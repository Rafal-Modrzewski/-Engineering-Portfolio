# Infrastructure Cost Governance

## The $5,000 Problem

Running AI products on GCP without governance leads to three failure modes:

### 1. Database Cost Spirals
**Symptom:** Connection pool exhaustion forces instance upgrades  
**Cost:** $420/month → $3,120/month (emergency scaling)

### 2. Serverless Bill Shocks  
**Symptom:** Cloud Run auto-scales to 100+ instances during traffic spikes  
**Cost:** $50/month → $800/month (single incident)

### 3. API Cost Explosions
**Symptom:** Infinite loops or DDoS hit LLM endpoints  
**Cost:** $100/month → $5,000/month (one bad deploy)

---

## My Solution: A Multi-Layer Defense System

I built **three interconnected governors** that prevent these failure modes:
```
┌─────────────────────────────────────────────┐
│        TOTAL COST GOVERNANCE                │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────────────┐                       │
│  │  PostgresGovernor │ ◄── You're here      │
│  │  (Database Layer) │                      │
│  └──────────────────┘                       │
│          ▼                                  │
│  Prevents: Connection exhaustion            │
│  Saves: approx.$1,300/month                 │
│  Portfolio: Fully documented                │
│                                             │
│  ┌──────────────────┐                       │
│  │ Cloud Run        │                       │
│  │ Controller       │                       │
│  └──────────────────┘                       │
│          ▼                                  │
│  Prevents: Instance explosions              │
│  Saves: $750/month                          │
│  Portfolio: Core logic                      │
│                                             │
│  ┌──────────────────┐                       │
│  │ Rate Limiter +   │                       │
│  │ Service Controls │                       │
│  └──────────────────┘                       │
│          ▼                                  │
│  Prevents: API abuse & infinite loops       │
│  Saves: $200/month                          │
│  Portfolio: Core logic                      │
│                                             │
│  Engineering time saved: 10h/mo = $1,000/mo

   TOTAL SAVINGS: ~$3,300/month               │
│  Investment Cost: $18/month (Cloud Run)     │
│                                             │
└─────────────────────────────────────────────┘
```

---

## Why Focus on PostgresGovernor in This Portfolio?

Of the three systems, **PostgresGovernor** is the most **architecturally interesting**:

### ✅ **Unique Technical Challenge**
- Priority-based connection termination (requires CTE query logic)
- Circuit breaker pattern (prevents governor from becoming the problem)
- Self-imposed resource limits (governor monitors itself)

### ✅ **Measurable Impact**
- 75% cost reduction 
- Zero DB outages in Q4 2025
- 94% autonomous recovery rate

### ✅ **Production Complexity**
- Handles connection saturation, long-running queries, deadlocks
- Graduated response system (warning → intervention → critical)
- Real-time telemetry with 30s monitoring loop

**The other two systems (Cloud Run, Rate Limiter) are important but more straightforward.**

---

## The Complete Architecture

### Database Layer: [PostgresGovernor](./database/)
**Problem:** Connection pool exhaustion forces expensive instance upgrades

**Solution:** Intelligent connection management with priority-based termination

**Key Innovation:**
```sql
-- Terminate connections by "disposability" not random selection
WITH ranked_connections AS (
    SELECT pid, state, duration,
        CASE 
            WHEN state = 'idle' THEN 1                 -- Zero user impact
            WHEN state = 'idle in transaction' THEN 2  -- Leaked connections
            WHEN state = 'active' THEN 3               -- Active work (only in CRITICAL)
        END as priority
    FROM pg_stat_activity
    ORDER BY priority, duration DESC
)
```

**[Read Full Documentation →](./database/README.md)**

---

### Compute Layer
**Problem:** Auto-scaling during traffic spikes causes $500+ monthly overages

**Solution:** Proactive instance limits and traffic migration

**Key Innovation:**
- Creates "restricted revisions" (256Mi RAM, 2 max instances)
- Gradual traffic migration with automatic rollback
- Health monitoring prevents bad deploys

**Portfolio Note:** 

Production implementation includes:
- Redis-based coordination for multi-region
- Metric aggregation from GCP Monitoring API
- Integration with service_controls.py for circuit breaking

---

### API Layer
**Problem:** Infinite loops or malicious traffic can trigger $1,000+ LLM API bills

**Solution:** Multi-window rate limiting + circuit breakers

**Key Innovation:**
- **Burst protection:** 30 requests/min prevents sudden spikes
- **Daily quotas:** 1,000 ops/day prevents runaway costs
- **Circuit breaker:** After 3 failures, stop trying and alert human

**Portfolio Note:** 

Production implementation includes:
- Distributed locking via Redis (prevents double-limiting in multi-instance deploys)
- Per-user quota tracking (B2B SaaS requirement)
- Integration with PostgresGovernor (prevents DB saturation from API traffic)

---


---

## Why This Matters for AI Products

Unlike traditional SaaS, AI products have **non-linear cost curves**:
```
Traditional SaaS: More users = More servers (predictable scaling)
AI SaaS: One bad user = $5,000 OpenAI bill (unpredictable)
```

**My governance layer makes AI costs predictable again.**

---

These systems work together. For example:

**Scenario:** User triggers 100 AI requests in 10 seconds
1. **Rate Limiter** blocks 70 requests (burst limit)
2. **Service Controls** circuit-breaks after 3 LLM failures
3. **PostgresGovernor** prevents DB saturation from the 30 allowed requests
4. **Cloud Run Controller** prevents instance explosion from traffic spike

**Total cost:** $2 (30 requests × $0.06)  
**Without governance:** $500+ (100 requests + forced DB upgrade + 50 Cloud Run instances)

---

## What's NOT Here (And Why)

You won't find:
- ❌ **Pub/Sub cost control** (not needed for my use case—API-driven, not event-driven)
- ❌ **Cloud Functions monitoring** (using Cloud Run instead)
- ❌ **Storage cost optimization** (negligible at SME scale)

For a different architecture (e.g., event-driven), I'd build different governors.

---

## Explore the Code

- **Start here:** [PostgresGovernor](./database/gcp_postgres_governor.py) (most complex)

**Testing Strategy:** See `tests/` directory.
