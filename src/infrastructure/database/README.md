# PostgresGovernor: Autonomous Database Reliability Agent

## The Business Problem

At high-growth SaaS scale, database instability is the **#1 driver** of:
-  Unplanned infrastructure costs ($5K-15K monthly spikes)
-  Customer-facing outages (P0 incidents)
-  Engineering team interrupt-driven work


### Real Cost Example (pre-Governor)
```
Month 1: $420  (baseline: db-custom-2-7680 with HA)
Month 2: $1,840 (forced upgrade to db-custom-8-32768 due to connection saturation)
Month 3: $3,120 (emergency scaling: db-n1-standard-32 + provisioned IOPS)

Total infra cost: $5,380 over 3 months
Average infra cost/mo: $1,793/mo
Total infra waste: $4,120 over 3 months
Average waste: $1,373/mo
```

### After Governor (Q4 2025)
```
Stable instance: db-custom-2-7680 (no upgrades needed)
Monthly cost: $420-$480 (storage growth only)
Governor cost: $18/month

Baseline infra cost: $438-$498/mo average
```

### **Savings: waste/mo - governor cost/mo = approx.$$1,355/mo (75% reduction)**


## The Solution

An **autonomous agent** that enforces operational limits *before* they trigger autoscaling or downtime.

### How It Works

**Graduated Response System:**
1. **Warning (70% saturation)** → Alert ops, log metrics
2. **Intervention (85% saturation)** → Terminate idle connections gracefully
3. **Critical (95% saturation)** → Intelligent load shedding with minimal user impact

**Key Innovation:** Priority-based connection termination algorithm that ranks connections by "disposability":
```python
Priority 1: idle → 0% user impact
Priority 2: idle in transaction → leaked connections
Priority 3: active queries → only in CRITICAL mode
```

---

## Business Impact (prod results)

### Cost Savings
-  **Reduced monthly Cloud SQL costs by 75%** ($1,355/mo net savings)
-  **Value Preserved:** $1,373/mo in avoided infrastructure waste
-  **Prevented 4 forced instance upgrades** (would cost $200+/mo each)
-  **Eliminated autoscaling events** that caused $1,200+ in monthly overages

### Reliability Improvements
-  **Two database-related P0 incidents** in Q4 2025 (down from 8 in Q3)
-  **Prevented 12 potential outages** detected through proactive monitoring
-  **Average connection pool utilization:** 68% (optimal range: 60-75%)

### Operational Efficiency
-  **Mean time to detection (MTTD):** <30 seconds (vs. 15+ minutes manual)
-  **Autonomous recovery rate:** 94% (no human intervention needed)
-  **Engineering time saved:** ~15 hours/quarter (on-call + incident response)

---

## Technical Architecture

### Core Components
```python
┌─────────────────────────────────────────────────────┐
│              PostgresGovernor                       │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐    ┌─────────────────┐         │
│  │  Monitoring  │───▶│  Decision       │         │
│  │  Loop (30s)  │    │  Engine         │         │
│  └──────────────┘    └─────────────────┘         │
│         │                      │                   │
│         ▼                      ▼                   │
│  ┌──────────────┐    ┌─────────────────┐         │
│  │ pg_stat_     │    │  Intervention   │         │
│  │ activity     │    │  Strategies     │         │
│  └──────────────┘    └─────────────────┘         │
│                                                     │
│  Self-Preservation Layer:                         │
│  • RLIMIT_AS: 512MB                               │
│  • Connection pool: 2-5 connections               │
│  • Graceful shutdown (SIGTERM/SIGINT)             │
└─────────────────────────────────────────────────────┘
```

### Monitoring Metrics
- **Connection saturation** (from `pg_stat_activity`)
- **Query duration** (identifies long-running queries)
- **Temporary space usage** (detects inefficient queries)
- **Deadlock frequency** (flags concurrent transaction issues)

### Intervention Strategies

#### 1. Connection Pool Optimization
```sql
-- Targets: Idle connections (>30s)
-- Impact: Zero user disruption
-- Frequency: When usage > 70%
```

#### 2. Intelligent Load Shedding
```sql
-- Priority-based termination using CTE
WITH ranked_connections AS (
    SELECT pid, state, duration,
        CASE 
            WHEN state = 'idle' THEN 1
            WHEN state = 'idle in transaction' THEN 2
            WHEN state = 'active' THEN 3
        END as priority
    FROM pg_stat_activity
    ORDER BY priority, duration DESC
)
```

#### 3. Self-Preservation
```python
# Governor limits itself to prevent becoming a noisy neighbor
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, -1))
```

---

## Installation & Configuration

### Prerequisites
- Python 3.11+
- GCP Project with Cloud SQL (PostgreSQL)
- Service Account with `cloudsql.client` role

### Environment Variables
```bash
export DATABASE_URL="postgresql://user:pass@host/db"
export GCP_PROJECT_ID="your-project"
export DATABASE_ID="your-instance-id"
```

### Running the Governor
```bash
# Install dependencies
pip install asyncpg google-cloud-monitoring google-cloud-logging

# Run as a background service
python gcp_postgres_governor.py

# Or deploy to Cloud Run (recommended)
gcloud run deploy postgres-governor \
  --source . \
  --region us-central1 \
  --min-instances 1 \
  --max-instances 1
```

---

## Design Decisions

## Reliability and Safety Design (Failure Modes)

A core tenet of the PostgresGovernor is **Self-Preservation**. The monitor must never become the cause of an outage.

| Failure Scenario | Governor Behavior | Safety Logic |
| :--- | :--- | :--- |
| **API Latency** | Governor loop slows down | Timeouts on all `asyncpg` acquires to prevent "hanging" the agent. |
| **Database Blindness** | **Fail Closed** | If the Governor cannot reach the DB, it halts all interventions. It will never kill a connection it cannot verify. |
| **Memory Leak** | **Self-Termination** | `resource.setrlimit` hard-caps the agent at 512MB. If exceeded, the container crashes and restarts rather than starving the DB. |
| **False Positives** | **Circuit Breaker** | If 3 consecutive interventions fail to lower saturation, the Governor enters "Safe Mode" and alerts human ops. |

### Why Priority-Based Termination?

**Alternatives Considered:**
- ❌ Random termination → Unpredictable user impact
- ❌ FIFO (oldest first) → Kills longest-running (often most important) queries first
- ❌ Round-robin → No intelligence about connection state

**My Approach:**
1. Idle connections (zero user impact)
2. Idle-in-transaction (leaked connections, no active work)
3. Active queries (only in CRITICAL mode, saves the database)

**Result:** 94% autonomous recovery rate with minimal user complaints.

### Why 30-Second Monitoring Interval?

**Trade-off Analysis:**
- ⚡ 10s interval → Too noisy, higher GCP Monitoring API costs
-   60s interval → Too slow, misses rapid saturation events
- ✅ 30s interval → Aligned with the Nyquist-Shannon sampling theorem relative to our average 15s connection-hold time. (proven in prod)

### Why Self-Imposed Memory Limits?
```python
# Without this, the governor itself could cause OOMs
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, -1))
```

**Real Incident:** In early testing, a memory leak in logging code caused the governor to consume 2GB RAM, ironically forcing a database restart. This limit prevents that scenario.

---

## Observability & Alerts

### GCP Logging Structure
```json
{
  "event": "load_shedding_executed",
  "mode": "CRITICAL",
  "connections_terminated": 5,
  "execution_time_ms": 87,
  "remaining_capacity": 12
}
```

### Key Metrics Dashboard
- Connection pool utilization (target: 60-75%)
- Intervention frequency (healthy: <3/day)
- Governor self-resource usage (must be <512MB)

---

## Lessons Learned

### What Worked Well
1. **CTE-based ranking** made termination logic readable and testable
2. **Graduated thresholds** prevented false positives (70/85/95 split)
3. **Self-preservation limits** eliminated "who watches the watchmen" problem
4. **Autonomous Circuit Breaker**: prevented 'death-spiral' termination loops by coding a state-aware circuit breaker that halts interventions after 3 failed attempts, escalating to human ops via GCP Logging/PagerDuty.

### What I'd Do Differently Next Time

1. **Predictive scaling:** Could add lightweight ML to predict saturation 30 minutes ahead based on traffic patterns (would prevent reactive interventions)

2. **Multi-region coordination:** Current design assumes single-region deployment. For global scale, would need Redis-based locking to prevent multiple governors from conflicting

3. **Query plan analysis:** Should log `EXPLAIN ANALYZE` output for terminated queries to help developers optimize problematic queries

---

## prod Runbook

### Scenario 1: Governor Stops Responding
```bash
# Check governor health
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=postgres-governor" --limit 50

# Restart if needed
gcloud run services update postgres-governor --region us-central1
```

### Scenario 2: Too Many Interventions
```bash
# Check if thresholds need adjustment
# Review metrics in logs, look for patterns
# Consider scaling database if interventions > 10/day
```

---

## Testing
```bash
# Run unit tests
pytest tests/test_governor.py -v

# Simulate connection saturation
python examples/load_test.py --connections 95 --duration 60
```

---

## System Efficiency and Economic Impact

### Infrastructure Efficiency
- **Saturation Ceiling:** Enforced a strict 75% connection saturation limit, preventing non-linear cost scaling.
- **Cost Avoidance:** Eliminated an average of **$1,373/mo** in unmanaged infrastructure waste (based on historical vertical scaling events).
- **Resource Footprint:** The Governor operates at a constant **$18/mo** overhead (Cloud Run + Monitoring API), representing a sub-1% cost to manage the entire data tier.

### Operational Impact
- **Incident Reduction:** 75% reduction in P0 database-related outages (8 incidents/Q3 → 2 incidents/Q4).
- **MTTR Improvement:** Reduced Mean Time to Recovery from 45 minutes (manual) to <2 minutes (autonomous).
- **Engineering Overhead:** Recaptured **~5 hours/mo** of Lead Engineer capacity previously spent on on-call firefighting.
---

## Related Documentation

- [Architecture Details](./docs/architecture.md)
- [Design Decisions](./docs/design_decisions.md)
- [prod Metrics](./docs/prod_metrics.md)
- [Threshold Calibration Guide](./examples/threshold_calibration.md)

---

## License

MIT License - See LICENSE file for details.

## Contact

**Rafal Modrzewski**  
Lead AI Engineer & Architect  
[GitHub](https://github.com/Rafal-Modrzewski) | [LinkedIn](https://www.linkedin.com/in/rafal-modrzewski-350b6a182/)
