"""
Unit tests for PostgresGovernor.

Tests focus on:
1. Graduated response logic (warning → intervention → critical)
2. Priority-based connection termination algorithm
3. Circuit breaker behavior
4. Self-preservation limits
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.infrastructure.gcp_postgres_governor import PostgresGovernor

@pytest.fixture
def mock_logger():
    """Mock GCP logger to avoid external dependencies."""
    with patch('google.cloud.logging.Client') as mock_client:
        mock_logger = MagicMock()
        mock_client.return_value.logger.return_value = mock_logger
        yield mock_logger

@pytest.fixture
def governor(mock_logger):
    """Create a governor instance with mocked dependencies."""
    # We patch setrlimit because it fails on some local OS environments (like Windows/Mac)
    with patch('resource.setrlimit'):
        gov = PostgresGovernor()
        return gov

@pytest.fixture
def mock_db_components():

    mock_pool = MagicMock() # acquire itself is not async, the context manager is
    mock_conn = AsyncMock() # The connection object has async methods (fetch, execute)
    
    # Setup the async context manager: async with pool.acquire() as conn:
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_conn
    mock_ctx.__aexit__.return_value = None
    
    mock_pool.acquire.return_value = mock_ctx
    
    return mock_pool, mock_conn

# --- TESTS ---

@pytest.mark.asyncio
async def test_graduated_response_warning_level(governor, mock_logger):
    metrics = {
        'conn_usage': 0.71,
        'max_duration': 10,
        'total_count': 14,
        'max_connections': 20
    }
    await governor._evaluate_and_act(metrics)
    assert any(c[0][0]['event'] == 'connection_saturation_warning' for c in mock_logger.log_struct.call_args_list)

@pytest.mark.asyncio
async def test_graduated_response_intervention_level(governor):
    metrics = {
        'conn_usage': 0.87,
        'max_duration': 10,
        'total_count': 17,
        'max_connections': 20
    }
    governor._optimize_pool = AsyncMock() # Spy
    await governor._evaluate_and_act(metrics)
    governor._optimize_pool.assert_called_once()

@pytest.mark.asyncio
async def test_graduated_response_critical_level(governor):
    metrics = {
        'conn_usage': 0.96,
        'max_duration': 10,
        'total_count': 19,
        'max_connections': 20
    }
    governor._shed_load = AsyncMock() # Spy
    await governor._evaluate_and_act(metrics)
    governor._shed_load.assert_called_once_with(metrics, mode='CRITICAL')

@pytest.mark.asyncio
async def test_priority_based_termination_logic(governor, mock_logger, mock_db_components):
    """
    Uses mock_db_components to  handle async context manager.
    """
    mock_pool, mock_conn = mock_db_components
    
    # Mock return: 2 idle connections
    mock_conn.fetch.return_value = [
        {'pid': 101, 'state': 'idle', 'duration': 600, 'query': 'SELECT 1', 'username': 'app', 'application_name': 'web'},
        {'pid': 102, 'state': 'idle', 'duration': 500, 'query': 'SELECT 2', 'username': 'app', 'application_name': 'web'}
    ]
    
    governor.db_pool = mock_pool
    
    metrics = {'total_count': 19, 'max_connections': 20}
    
    await governor._shed_load(metrics, mode='INTERVENTION')
    
    # Now this will pass because the code actually executed
    assert mock_conn.execute.call_count == 2

@pytest.mark.asyncio
async def test_circuit_breaker_triggers_after_three_failures(governor):
    """Test that circuit breaker engages after 3 failed interventions."""
    governor._intervention_attempts = 3
    
    governor._last_intervention_time = time.time() 
    
    assert governor._should_trigger_circuit_breaker() is True

@pytest.mark.asyncio
async def test_circuit_breaker_resets_after_timeout(governor):
    """Test that circuit breaker resets after 5 minutes of stability."""
    governor._intervention_attempts = 3
    governor._last_intervention_time = time.time() - 360 # 6 mins ago
    
    assert governor._should_trigger_circuit_breaker() is False
    
    safe_metrics = {'conn_usage': 0.5, 'max_duration': 5} 
    await governor._evaluate_and_act(safe_metrics)
    
    assert governor._intervention_attempts == 0

@pytest.mark.asyncio
async def test_telemetry_gathering_handles_errors_gracefully(governor, mock_logger, mock_db_components):
    """Test that telemetry gathering doesn't crash on database errors."""

    mock_pool, mock_conn = mock_db_components
    
    mock_conn.fetchrow.side_effect = Exception("Connection timeout")
    governor.db_pool = mock_pool
    
    result = await governor._gather_telemetry()
    
    assert result == {}
    assert any('telemetry_gathering_failed' in str(c) for c in mock_logger.log_struct.call_args_list)

@pytest.mark.asyncio
async def test_long_running_query_termination(governor, mock_db_components):
    """Test that queries exceeding critical duration are terminated."""
    
    mock_pool, mock_conn = mock_db_components
    
    mock_conn.fetch.return_value = [
        {'pid': 201, 'query': 'SELECT slow', 'duration': 50}
    ]
    
    governor.db_pool = mock_pool
    metrics = {'max_duration': 50}
    
    await governor._terminate_long_running_queries(metrics)
    
    mock_conn.execute.assert_called_once()


def test_resource_limits_are_configured(governor, mock_logger):
    """Test that memory limits are set during initialization."""
    with patch('gcp_postgres_governor.resource.setrlimit') as mock_setrlimit:
        gov = PostgresGovernor()
        
        # Should set RLIMIT_AS to 512MB
        mock_setrlimit.assert_called_once()
        args = mock_setrlimit.call_args[0]
        assert args[1] == (512 * 1024 * 1024, -1)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
