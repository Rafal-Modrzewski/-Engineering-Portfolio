# PostgresGovernor Architecture

## System Overview
````
┌─────────────────────────────────────────────────────────────────┐
│                    PostgresGovernor                             │
│                   (Cloud Run Service)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐         ┌─────────────────────┐              │
│  │  Monitoring  │────────▶│  Telemetry          │              │
│  │  Loop (30s)  │         │  Aggregator         │              │
│  └──────────────┘         └─────────────────────┘              │
│         │                           │                            │
│         │                           ▼                            │
│         │                  ┌──────────────────┐                 │
│         │                  │  pg_stat_        │                 │
│         │                  │  activity        │                 │
│         │                  └──────────────────┘                 │
│         │                           │                            │
│         ▼                           ▼                            │
│  ┌──────────────────────────────────────────┐                  │
│  │      Decision Engine                     │                  │
│  │                                           │                  │
│  │  if conn_usage > 0.95:                   │                  │
│  │      → _shed_load(CRITICAL)              │                  │
│  │  elif conn_usage > 0.85:                 │                  │
│  │      → _optimize_pool()                  │                  │
│  │  elif conn_usage > 0.70:                 │                  │
│  │      → log_warning()                     │                  │
│  └──────────────────────────────────────────┘                  │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────┐                  │
│  │  Intervention Strategies                 │                  │
│  │                                           │                  │
│  │  • Idle connection termination           │                  │
│  │  • Priority-based load shedding          │                  │
│  │  • Long-running query termination        │                  │
│  └──────────────────────────────────────────┘                  │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────┐                  │
│  │  Self-Preservation Layer                 │                  │
│  │                                           │                  │
│  │  • RLIMIT_AS: 512MB                      │                  │
│  │  • Connection pool: 2-5 connections      │                  │
│  │  • Graceful shutdown (SIGTERM/SIGINT)    │                  │
│  └──────────────────────────────────────────┘                  │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────────────────────────────────┐                  │
│  │  Observability                           │                  │
│  │                                           │                  │
│  │  GCP Logging (JSON structured logs)      │                  │
│  │  • Event tracking                        │                  │
│  │  • Performance metrics                   │                  │
│  │  • Error context                         │                  │
│  └──────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │   Cloud SQL (PostgreSQL)     │
              │                              │
              │   • pg_stat_activity         │
              │   • pg_terminate_backend()   │
              └──────────────────────────────┘
Data Flow
1. Monitoring Phase (every 30s)
pythonmetrics = {
    'conn_usage': 0.87,       # 87% of max_connections
    'max_duration': 23,       # Longest running query
    'active_count': 12,
    'idle_count': 5,
    'idle_in_tx_count': 1
}
2. Decision Phase
pythonif metrics['conn_usage'] > 0.95:
    # CRITICAL: Database at risk of exhaustion
    await _shed_load(mode='CRITICAL', limit=5)
    
elif metrics['conn_usage'] > 0.85:
    # INTERVENTION: Proactive cleanup
    await _optimize_pool()  # Terminates idle connections
    
elif metrics['conn_usage'] > 0.70:
    # WARNING: Monitor closely
    logger.log_warning('Connection usage elevated')
3. Intervention Phase
sql-- Priority-based termination query
WITH ranked_connections AS (
    SELECT pid, state, duration,
        CASE 
            WHEN state = 'idle' THEN 1                 -- Safest to terminate
            WHEN state = 'idle in transaction' THEN 2  -- Likely leaked
            WHEN state = 'active' THEN 3               -- Active work
        END as priority
    FROM pg_stat_activity
    WHERE backend_type = 'client backend'
    ORDER BY priority, duration DESC
    LIMIT 5
)
SELECT pg_terminate_backend(pid) FROM ranked_connections;
Component Details
Monitoring Loop

Frequency: 30 seconds
Rationale: Balance between detection speed and API costs
Failure Mode: 5-second backoff on errors

Decision Engine

Input: Real-time metrics from pg_stat_activity
Output: Intervention command (or no-op)
State: Stateless (no persistence between loops)

Intervention Strategies
1. Pool Optimization (85% threshold)

Target: Idle connections >300 seconds
Impact: Zero user disruption
Frequency: As needed (typically <3/day)

2. Load Shedding (95% threshold)

Target: Ranked connections by priority
Impact: Minimal (targets idle first)
Frequency: Rare (<<1/day in healthy system)

Self-Preservation
python# Prevent governor from becoming the problem
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, -1))
Deployment
Cloud Run Configuration
yamlservice: postgres-governor
runtime: python311
memory: 512Mi
min_instances: 1
max_instances: 1  # Singleton pattern
env_variables:
  DATABASE_URL: ${DATABASE_URL}
  GCP_PROJECT_ID: ${PROJECT_ID}
Required Permissions
yamlroles:
  - cloudsql.client
  - logging.logWriter
  - monitoring.metricWriter
````

## Failure Modes

### 1. Governor Crashes
- **Impact:** Monitoring stops, database unprotected
- **Mitigation:** Cloud Run auto-restarts (<10s downtime)

### 2. Intervention Fails
- **Circuit Breaker:** After 3 failures, escalate to human
- **Fallback:** Stop autonomous actions to prevent thrashing

### 3. Database Unreachable
- **Behavior:** Log error, continue monitoring
- **Recovery:** Auto-resume when connection restored

## Performance Characteristics

- **Memory footprint:** 50-200MB (under 512MB limit)
- **CPU usage:** <5% (minimal processing)
- **Network:** ~1KB/30s (telemetry query)
- **Latency:** <100ms per monitoring cycle
````
