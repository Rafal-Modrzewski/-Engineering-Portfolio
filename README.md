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

### 🛡️ [Layer 1: Infrastructure Governance](src/infrastructure)

*   **Business Problem:** Uncontrolled DB scaling ($420 → $3,000 spikes) due to AI-driven connection saturation.
*   **Architectural Solution:** Autonomous agent that enforces saturation ceilings via priority-based connection termination (CTE-logic).
*   **Tech**: Python, Asyncpg, GCP Monitoring API.

**PostgresGovernor (Autonomous Database Agent)** Prevents infrastructure cost spirals by enforcing strict saturation limits.
- **Economic Impact:** $1,355/mo in peak net cost avoidance (75% reduction vs unmanaged spikes).
- **Operational Impact:** Reduced P0 database incidents from 8/quarter to 2.

[View Code →](src/infrastructure/gcp_postgres_governor.py)

### 🤖 [Layer 2: AI Orchestration](src/backend/)

*  **Business Problem**: Non-deterministic nature of LLMs poses a compliance and stability risk in B2B workflows.
*  **Solution**: A strict State Machine architecture enforced via Python decorators.
  - **Logic**: The @require_valid_campaign decorator (see tests/) and lenient parsing with JSON5 enforces rigid state transitions. This ensures that while AI content is probabilistic, the business workflow remains 100% deterministic and auditable.
  - **Testing**: Unit tests (Pytest) verify state integrity and error handling without external dependencies.
  - **Tech**: Python 3.12, FastAPI, SQLAlchemy (Async), State Machine Pattern.

**Deterministic State Machine** Wraps non-deterministic LLMs in rigid, auditable workflows.
- **Economic Impact:** Eliminated $1,000+ wasted tokens on invalid request states.
- **Operational Impact:** Robust audit trail for B2B compliance; 94% reduction in parsing failures.

[View Code →](src/backend/deterministic_ai_service.py)

### ⚡ [Layer 3: User Experience](src/frontend/)

* **Business Problem**: High latency of LLM inference degrades user trust and retention.
* **Solution**: Optimistic UI patterns and robust state management.

**Optimistic UI & State Reconciliation** Decouples expensive inference latency from perceived user speed.
- **Product Impact:** Maintained 4.2s perceived latency (vs 12s actual).
- **Technical Innovation:** State reconciliation pattern for async AI streams.
- **Tech**: TypeScript, React, Optimistic Updates.

  
[View Code →](src/frontend/StrategicChatView.tsx)

---

## Systems Architecture

To respect the reviewer's time, this repository shows a ** selection** of the most architecturally important components. 

In prod, these systems operate within a broader governance framework I architected, including:
*   **Cloud Run Controller:** Prevents serverless bill shocks via restricted revision jailing.
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

## How to Validate (Run Tests)

This repo includes a robust test suite to verify the core deterministic AI service (AI Orchestration) and cloud Infrastructure Governance.

**1. Install dependencies:**
```bash
pip install -r requirements.txt
```

**2. Run the full test suite:**

#### ✅ Expected Outcome

Running the suite validates both the Infrastructure Governor and the deterministic AI service logic, ensuring end-to-end reliability.

```
=========================== test session starts ============================
collected 14 items
tests/infrastructure/test_governor.py ......... [ 64%]
tests/backend/test_ai_service.py ..... [100%]
======================== 14 passed in 0.82s ========================
```

[View Tests →](src/tests/)

## Contact
**Rafal Modrzewski**  
Lead AI Architect & Founder @ Stratik.co   | Architecture Strategy  
[LinkedIn](https://www.linkedin.com/in/rafal-modrzewski-350b6a182/) 

