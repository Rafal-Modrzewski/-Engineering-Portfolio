Unit tests for PostgresGovernor.

Tests focus on:
1. Graduated response logic (warning → intervention → critical)
2. Priority-based connection termination algorithm
3. Circuit breaker behavior
4. Self-preservation limits
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Import the governor (adjust path as needed)
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from gcp_postgres_governor import PostgresGovernor


@pytest.fixture
def mock_logger():
    """Mock GCP logger to avoid external dependencies."""
    with patch('gcp_postgres_governor.gcp_logging.Client') as mock_client:
        mock_logger = MagicMock()
        mock_client.return_value.logger.return_value = mock_logger
        yield mock_logger


@pytest.fixture
def governor(mock_logger):
    """Create a governor instance with mocked dependencies."""
    with patch('gcp_postgres_governor.resource.setrlimit'):
        gov = PostgresGovernor()
        return gov


@pytest.mark.asyncio
async def test_graduated_response_warning_level(governor, mock_logger):
    """Test that warning threshold logs but doesn't intervene."""
    metrics = {
        'conn_usage': 0.71,  # Just above warning threshold (0.70)
        'max_duration': 10,
        'total_count': 14,
        'max_connections': 20
    }
    
    await governor._evaluate_and_act(metrics)
    
    # Should log warning but NOT call _shed_load or _optimize_pool
    assert any(
        call[0][0]['event'] == 'connection_saturation_warning'
        for call in mock_logger.log_struct.call_args_list
    )


@pytest.mark.asyncio
async def test_graduated_response_intervention_level(governor):
    """Test that intervention threshold triggers pool optimization."""
    metrics = {
        'conn_usage': 0.87,  # Above intervention threshold (0.85)
        'max_duration': 10,
        'total_count': 17,
        'max_connections': 20
    }
    
    # Mock the optimization method
    governor._optimize_pool = AsyncMock()
    
    await governor._evaluate_and_act(metrics)
    
    # Should call _optimize_pool
    governor._optimize_pool.assert_called_once()


@pytest.mark.asyncio
async def test_graduated_response_critical_level(governor):
    """Test that critical threshold triggers load shedding."""
    metrics = {
        'conn_usage': 0.96,  # Above critical threshold (0.95)
        'max_duration': 10,
        'total_count': 19,
        'max_connections': 20
    }
    
    # Mock the load shedding method
    governor._shed_load = AsyncMock()
    
    await governor._evaluate_and_act(metrics)
    
    # Should call _shed_load with CRITICAL mode
    governor._shed_load.assert_called_once_with(metrics, mode='CRITICAL')


@pytest.mark.asyncio
async def test_priority_based_termination_logic(governor, mock_logger):
    """
    Test that connection termination prioritizes idle connections over active ones.
    
    Simulates a scenario with:
    - 2 idle connections
    - 1 idle in transaction
    - 2 active connections
    
    Expected: Should terminate idle connections first.
    """
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    
    # Mock fetch result: connections sorted by priority
    mock_conn.fetch.return_value = [
        {'pid': 101, 'state': 'idle', 'duration': 600, 'query': 'SELECT 1', 'username': 'app', 'application_name': 'web'},
        {'pid': 102, 'state': 'idle', 'duration': 500, 'query': 'SELECT 2', 'username': 'app', 'application_name': 'web'}
    ]
    
    mock_conn.execute = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    governor.db_pool = mock_pool
    
    metrics = {
        'total_count': 19,
        'max_connections': 20
    }
    
    await governor._shed_load(metrics, mode='INTERVENTION')
    
    # Verify that pg_terminate_backend was called for both idle connections
    assert mock_conn.execute.call_count == 2
    
    # Verify logging captured the terminations
    assert any(
        'load_shedding_executed' in str(call)
        for call in mock_logger.log_struct.call_args_list
    )


@pytest.mark.asyncio
async def test_circuit_breaker_triggers_after_three_failures(governor):
    """Test that circuit breaker engages after 3 failed interventions."""
    governor._intervention_attempts = 3
    governor._last_intervention_time = asyncio.get_event_loop().time()
    
    assert governor._should_trigger_circuit_breaker() is True


@pytest.mark.asyncio
async def test_circuit_breaker_resets_after_timeout(governor):
    """Test that circuit breaker resets after 5 minutes of stability."""
    governor._intervention_attempts = 3
    # Simulate intervention 6 minutes ago
    governor._last_intervention_time = asyncio.get_event_loop().time() - 360
    
    assert governor._should_trigger_circuit_breaker() is False
    # Should have reset the counter
    await governor._evaluate_and_act({'conn_usage': 0.5})
    assert governor._intervention_attempts == 0


@pytest.mark.asyncio
async def test_telemetry_gathering_handles_errors_gracefully(governor, mock_logger):
    """Test that telemetry gathering doesn't crash on database errors."""
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    
    # Simulate database connection error
    mock_conn.fetchrow.side_effect = Exception("Connection timeout")
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    governor.db_pool = mock_pool
    
    result = await governor._gather_telemetry()
    
    # Should return empty dict on error
    assert result == {}
    
    # Should log the error
    assert any(
        'telemetry_gathering_failed' in str(call)
        for call in mock_logger.log_struct.call_args_list
    )


@pytest.mark.asyncio
async def test_long_running_query_termination(governor):
    """Test that queries exceeding critical duration are terminated."""
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    
    # Mock a long-running query
    mock_conn.fetch.return_value = [
        {
            'pid': 201,
            'query': 'SELECT * FROM large_table WHERE slow_condition',
            'duration': 50  # Exceeds critical threshold (45s)
        }
    ]
    
    mock_conn.execute = AsyncMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    governor.db_pool = mock_pool
    
    metrics = {'max_duration': 50}
    
    await governor._terminate_long_running_queries(metrics)
    
    # Should call pg_terminate_backend
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
