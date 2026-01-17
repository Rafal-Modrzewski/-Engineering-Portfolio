#src/1_infrastructure/gcp_postgres_governor.py

"""
An autonomous governor for a Cloud SQL for PostgreSQL instance, designed to
ensure stability and prevent catastrophic cost spikes for an early-stage SaaS.

My Philosophy:

For a bootstrapped product, the primary infrastructure risks are not just about
performance, but also about cost and stability. For a startup a surprise cloud bill or a database
overload can be an existential threat, while for an enterprise an iefficent use of funds! This file targets the real-world
drivers of these problems like... hanging transactions,
connection pool exhaustion, and long-running queries that force a premature,
expensive upgrade to the next instance tier.

I built the system on principle of Graduated Response (deal with the biggest fire 🔥 first without disrupting user experience) . 

Script first attempts to optimize, then gracefully intervenes, and only as final step takes aggressive action in a
critical scenario to ensure the core application remains stable and online.

"""

import os
import signal
import time
from datetime import datetime, timezone
from typing import Dict
from concurrent.futures import ThreadPoolExecutor
import resource

import asyncpg
import asyncio
import aiohttp
from google.cloud import monitoring_v3
from google.cloud import logging as gcp_logging
from redis.asyncio import Redis

# --- Configuration (Values are set via environment variables in production) ---
DB_CONFIG = {
    'db_name': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST')
}

REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', 6379))
}


class PostgresGovernor:
    """
    Manages a PostgreSQL database to ensure stability and control costs
    by monitoring key metrics and performing tiered interventions.
    """

    def __init__(self):
        self.PROJECT_ID = os.getenv('GCP_PROJECT_ID')
        if not self.PROJECT_ID:
            raise ValueError("GCP_PROJECT_ID environment variable not set.")

        self.LOCATION = os.getenv('GCP_LOCATION', 'us-west1')
        self.DATABASE_ID = os.getenv('DATABASE_ID')
        if not self.DATABASE_ID:
            raise ValueError("DATABASE_ID environment variable not set.")

        # --- GCP Clients ---
        self.monitoring_client = monitoring_v3.MetricServiceClient()
        self.logging_client = gcp_logging.Client()
        self.logger = self.logging_client.logger('postgres-governor')

        # --- Database & Redis Pools ---
        self.db_pool = None
        self.redis = Redis(**REDIS_CONFIG)

        # --- Thread Pools for Blocking I/O ---
        self._metric_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="metric_worker")
        self._db_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="db_worker")

        # --- Intervention Thresholds ---
        # These values are set conservatively for a small instance (e.g., db-g1-small)
        # to prevent issues long before they become critical.
        self.THRESHOLDS = {
            'connection_total': {
                'warning': 9,        # Action: Optimize pool
                'intervention': 15,  # Action: Terminate 2 idle connections
                'critical': 17       # Action: Terminate 5 connections aggressively
            },
            'query_duration_seconds': {
                'warning': 15,       # Action: Log query for analysis
                'critical': 25       # Action: Terminate query
            },
            'temp_space_mb': {
                'warning': 200,      # Action: Clear unused temp tables
                'intervention': 320, # Action: Terminate 1 large temp space query
                'critical': 400      # Action: Terminate 5 large temp space queries
            },
            'deadlock_count': {
                'warning': 1,        # Action: Log and attempt graceful termination
                'critical': 3        # Action: Forcefully terminate deadlocked processes
            },
            'cpu_utilization_percent': {
                'warning': 70,
                'intervention': 85,
                'critical': 90
            }
        }

        # --- State ---
        self.in_emergency_mode = False
        self._shutdown_flag = False

        # --- Process Setup ---
        self._register_signal_handlers()
        self._configure_resource_limits()

    async def start(self):
        """Initializes connections and starts the governor."""
        try:
            self.logger.log_struct({'event': 'governor_starting'})
            await self._create_db_pool()
            self.logger.log_struct({'event': 'governor_started'})
            # In a full implementation, this would kick off the monitoring loop.
        except Exception as e:
            self.logger.log_struct({
                'event': 'governor_startup_failed',
                'error': str(e)
            }, severity='CRITICAL')
            raise

    async def stop(self):
        """Gracefully stops the governor and cleans up connections."""
        try:
            self.logger.log_struct({'event': 'governor_stopping'})
            if self.db_pool:
                await self.db_pool.close()
            self._metric_pool.shutdown(wait=True)
            self._db_pool.shutdown(wait=True)
            self.logger.log_struct({'event': 'governor_stopped'})
        except Exception as e:
            self.logger.log_struct({
                'event': 'governor_stop_failed',
                'error': str(e)
            }, severity='ERROR')
            raise

    # ... (Rest of the methods would go here, such as monitor_database + graduated intervention functions) ...
    # This portfolio focuses on the setup, philosophy, and 1 key intervention.
 
    async def _create_db_pool(self):
        """Creates the asyncpg database connection pool."""
        try:
            self.db_pool = await asyncpg.create_pool(
                database=DB_CONFIG['db_name'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                host=DB_CONFIG['host'],
                min_size=2,
                max_size=10
            )
            self.logger.log_struct({'event': 'db_pool_created'})
        except Exception as e:
            self.logger.log_struct({
                'event': 'db_pool_creation_failed', 'error': str(e)
            }, severity='CRITICAL')
            raise

    def _configure_resource_limits(self):
        """Sets memory limits for the governor process itself to prevent run-away costs."""
        try:
            # Set a soft memory limit of 512MB.
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, -1))
            self.logger.log_struct({'event': 'resource_limits_set', 'memory_limit_mb': 512})
        except Exception as e:
            self.logger.log_struct({
                'event': 'resource_limit_setting_failed', 'error': str(e)
            }, severity='WARNING')

    def _register_signal_handlers(self):
        """Registers handlers for SIGTERM and SIGINT for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Sets the shutdown flag upon receiving a signal."""
        self.logger.log_struct({'event': 'shutdown_signal_received', 'signal': signum})
        self._shutdown_flag = True


    async def _terminate_longest_running_connections(self, num_to_terminate: int, is_critical: bool):
        """
        A key intervention function that intelligently terminates connections
        based on a priority system to minimize disruption.

        Termination Priority:
        1. Idle connections (least disruptive)
        2. Idle in transaction
        3. Active queries (most disruptive)

        In a non-critical situation, it avoids terminating active transactions.
        In a critical situation, it will terminate any connection to save the database.

        Args:
            num_to_terminate: The number of connections to terminate.
            is_critical: A boolean flag to enable aggressive termination.
        """
        try:
            async with self.db_pool.acquire() as conn:
                # This CTE-based query ranks connections by how disruptive their
                # termination would be, ensuring we always terminate the "safest"
                # connections first.
                query = """
                    WITH ranked_connections AS (
                        SELECT
                            pid,
                            state,
                            GREATEST(
                                EXTRACT(EPOCH FROM (now() - query_start)),
                                EXTRACT(EPOCH FROM (now() - xact_start))
                            ) as duration_seconds,
                            CASE
                                WHEN state = 'idle' THEN 1
                                WHEN state = 'idle in transaction' THEN 2
                                WHEN state = 'active' THEN 3
                            END as termination_priority
                        FROM pg_stat_activity
                        WHERE
                            backend_type = 'client backend'
                            AND pid <> pg_backend_pid()
                            {extra_conditions}
                        ORDER BY
                            termination_priority,
                            duration_seconds DESC
                        LIMIT $1
                    )
                    SELECT pid, state, duration_seconds FROM ranked_connections;
                """

                extra_conditions = "" if is_critical else "AND (state != 'active' OR backend_xid IS NULL)"
                full_query = query.format(extra_conditions=extra_conditions)

                connections_to_terminate = await conn.fetch(full_query, num_to_terminate)

                for conn_info in connections_to_terminate:
                    pid = conn_info['pid']
                    # In a real implementation, this calls a graceful termination
                    # function for non-critical and pg_terminate_backend for critical.
                    await conn.execute("SELECT pg_terminate_backend($1);", pid)

                if connections_to_terminate:
                    self.logger.log_struct({
                        'event': 'connections_terminated',
                        'count': len(connections_to_terminate),
                        'level': 'CRITICAL' if is_critical else 'INTERVENTION',
                        'details': [{
                            'pid': r['pid'], 'state': r['state'], 'duration': r['duration_seconds']
                        } for r in connections_to_terminate]
                    }, severity='CRITICAL' if is_critical else 'WARNING')

        except Exception as e:
            self.logger.log_struct({
                'event': 'connection_termination_error', 'error': str(e)
            }, severity='ERROR')




