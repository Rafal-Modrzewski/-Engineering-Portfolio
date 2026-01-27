# Engineering Strategy & Governance Portfolio: Rafal Modrzewski

**Role:** Lead AI Architect & Founder @ Stratik.co  
**Focus:** AI Unit Economics, System Governance, Production Reliability

---

## The Problem I Solve
Scaling AI products creates three existential business risks:
1. **Financial Risk** - Ungoverned LLM APIs and database auto-scaling can destroy margins.
2. **Operational Risk** - Non-deterministic AI behavior creates support tickets and compliance failures.
3. **Product Risk** — High inference latency (10s+) kills user retention and conversion.

---

## The Solution: A Three-Layer Defense System

### 🛡️ [Layer 1: Infrastructure Governance](src/1_infrastructure)
**PostgresGovernor (Autonomous Database Agent)**
Prevents infrastructure cost spirals by enforcing strict saturation limits.
- **Economic Impact:** $1,355/mo in peak net cost avoidance (75% reduction vs unmanaged spikes).
- **Operational Impact:** Reduced P0 database incidents from 8/quarter to 2.

[View Code →](src/1_infrastructure/)

### 🤖 [Layer 2: AI Orchestration](src/2_backend/)
**Deterministic State Machine**
Wraps non-deterministic LLMs in rigid, auditable workflows.
- **Economic Impact:** Eliminated $1,000+ wasted tokens on invalid request states.
- **Operational Impact:** Robust audit trail for B2B compliance; 94% reduction in parsing failures.

[View Code →](src/2_backend/)

### ⚡ [Layer 3: User Experience](src/3_frontend/)
**Optimistic UI & State Reconciliation**
Decouples expensive inference latency from perceived user speed.
- **Product Impact:** Maintained 4.2s perceived latency (vs 12s actual).
- **Technical Innovation:** State reconciliation pattern for async AI streams.

[View Code →](src/3_frontend/)

---

## The "Hidden" Ecosystem (Systems Architecture)

To respect the reviewer's time, this repository showcases a **curated selection** of the most architecturally significant components. 

In production, these systems operate within a broader governance framework I architected, including:
*   **Cloud Run Controller:** Prevents serverless bill shocks via "Restricted Revision" jailing.
*   **API Rate Limiters:** Redis-backed circuit breakers to prevent LLM loops.
*   **Service Controls:** Per-user quota management to enforce SaaS margin targets.

**These additional components are available for deep-dive discussion.**

---

## Why This Approach?

I built Stratik.co (B2B SaaS) from scratch. As lean company, I had to architect for **profitability from day one**.

**This portfolio demonstrates:**
1.  **Economic Engineering:** Every line of code is measured by its P&L impact.
2.  **Fail-Safe Design:** Systems that default to safety (Fail Closed) rather than burning cash.
3.  **Strategic Curation:** Solving the hardest problems (Reliability) first.

---

## Quick Stats (Q4 2025)

| Metric | Result |
| :--- | :--- |
| **Peak Cost Avoidance** | **~$3,300/mo** (Combined Database + Compute + API + Engineering Time) |
| **Workflow Determinism** | **99.9%** (Negligible number of invalid-state AI calls) |
| **Test Coverage** | **94%** (Critical path coverage) |

---

## 🛠️ How to Validate (Run Tests)

This repository includes a test suite to verify the business logic integrity using **Pytest** and **AsyncMock**.

```bash
# 1. Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio

# 2. Run the test suite
python -m pytest
```

### 4. Expected test outcome

tests/test_business_logic.py ......                                [100%]
======================== 6 passed, 1 warning in 0.97s =========================

## Contact
**Rafal Modrzewski**  
Lead AI Architect | Architecture Strategy  
[LinkedIn](https://www.linkedin.com/in/rafal-modrzewski-350b6a182/) 

