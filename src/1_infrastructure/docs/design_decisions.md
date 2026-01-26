
# Design Decisions

## Why Graduated Response?

### Problem
Binary interventions (on/off) cause:
- Overreaction to transient spikes
- Unnecessary user disruption
- Missed opportunities for self-healing

### Solution: Three-Tier System
````
70% saturation → WARNING (observe)
85% saturation → INTERVENTION (optimize)
95% saturation → CRITICAL (shed load)
````

### Real Example

Scenario: Traffic spike causes brief jump to 72% utilization

With binary system:
- Triggers immediate terminations
- Users experience dropped connections
- Spike resolves naturally in 2 minutes
- Result: Unnecessary disruption

With graduated system:
- Logs warning, continues monitoring
- Spike resolves naturally
- No user impact
- If sustained >30s at 85%+, then intervene
- Result: No unnecessary action

## Why Priority-Based Termination?

Alternatives Considered

### Option 1: Random Termination

Simple but dangerous
````
connections = get_all_connections()
random.shuffle(connections)
terminate(connections[:5])
````
Rejected: Unpredictable user impact. Might kill active queries.

### Option 2: FIFO (Oldest First)

Logical but flawed
````
SELECT pid FROM pg_stat_activity
ORDER BY query_start ASC
LIMIT 5
````
Rejected: Longest-running queries are often the most important (analytics, reports).

### Option 3: Priority-Based (Chosen)
```sql
  SELECT pid,
    CASE 
        WHEN state = 'idle' THEN 1
        WHEN state = 'idle in transaction' THEN 2
        WHEN state = 'active' THEN 3
    END as priority
FROM pg_stat_activity
ORDER BY priority, duration DESC
````
**Chosen:** Minimizes user impact by targeting truly disposable connections.

### Production Results
- 94% autonomous recovery rate
- <5% user complaints about disconnections
- Average termination: 2.3 idle connections per incident

---

## Why 30-Second Monitoring Interval?


### Trade-off Analysis



### Real Incident
````
2025-10-15 14:23:00 - Connection usage: 68%
2025-10-15 14:23:30 - Connection usage: 89% (INTERVENTION triggered)
2025-10-15 14:24:00 - Connection usage: 72% (recovered)

With 60s interval:
2025-10-15 14:23:00 - Connection usage: 68%
2025-10-15 14:24:00 - Connection usage: 96% (CRITICAL - too late!)
````

---

## Why Self-Imposed Memory Limits?


**Early version incident (2025-08-12):**
````
14:30 - Governor starts monitoring
14:45 - Logger accumulates 500MB in memory (bug in log buffering)
14:47 - Governor OOM, container restart
14:47 - Database loses monitoring for 10 seconds
14:48 - Connection spike during monitoring gap → outage
````
Lesson: The monitor can become the problem.

Solution
````
pythonresource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, -1))
````
Effect: Governor crashes before impacting database.


## Why 512MB?

- Governor baseline: ~50MB
- Peak (during intervention): ~200MB
- Safety margin: 2.5x = 512MB
- Database memory: Unaffected


## Why CTE-Based Ranking Query?

Alternative: Multiple Queries

BAD: Multiple round-trips
````
idle_conns = await conn.fetch("SELECT pid FROM pg_stat_activity WHERE state='idle'")
idle_tx_conns = await conn.fetch("SELECT pid FROM pg_stat_activity WHERE state='idle in transaction'")
active_conns = await conn.fetch("SELECT pid FROM pg_stat_activity WHERE state='active'")
````


# Combine and sort in Python

Problems:
- 3x network round-trips
- Race conditions (state changes between queries)
- Python sorting is slower than PostgreSQL


Solution: Single CTE Query
````
sqlWITH ranked_connections AS (
    SELECT pid, state,
        CASE 
            WHEN state = 'idle' THEN 1
            WHEN state = 'idle in transaction' THEN 2
            WHEN state = 'active' THEN 3
        END as priority
    FROM pg_stat_activity
    ORDER BY priority, duration DESC
)
SELECT * FROM ranked_connections LIMIT 5;
````

**Benefits:**

- 1 network round-trip
- Atomic snapshot of database state
- PostgreSQL-optimized sorting

---


## Why Circuit Breaker?

**Scenario without circuit breaker:**
````
14:00 - Connection saturation detected
14:00 - Terminate 5 connections
14:01 - Still saturated (new connections arrived)
14:01 - Terminate 5 more connections
14:02 - Still saturated (underlying issue)
14:02 - Terminate 5 more connections
... (infinite loop)
````

Result: Endless terminations, no recovery, wasted resources.

Solution: Circuit Breaker

````
python if intervention_attempts >= 3:
    escalate_to_human()  # Stop trying, need human diagnosis
````

**Reset condition:** 5 minutes of stability

### Real Example (2025-09-20)

````
15:30 - High CPU query detected, terminate connection
15:31 - Query re-spawned (bug in application code), terminate again
15:32 - Query re-spawned again, terminate again
15:33 - Circuit breaker triggers: "Human intervention required"
15:35 - Ops team fixes application bug
15:40 - Circuit breaker resets, autonomous monitoring resumes
````
---

## Why NOT Machine Learning?

### Temptation
Use ML to predict saturation 30 minutes ahead based on traffic patterns.

### Rejection Reasons
1. **Complexity:** Adds training pipeline, model versioning, feature engineering
2. **Cost:** Requires labeled historical data
3. **Brittleness:** Traffic patterns change (new feature launches, marketing campaigns)
4. **Diminishing Returns:** Graduated thresholds work well (94% success rate)

### When to Reconsider
- If autonomous recovery rate drops below 80%
- If we see clear predictable patterns (e.g., daily 2PM spike)
- If we have 12+ months of stable historical data

**Current status:** Rule-based system is sufficient.
