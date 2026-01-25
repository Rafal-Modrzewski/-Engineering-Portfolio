# Engineering Portfolio: Rafal Modrzewski

**Role:** Lead AI Engineer & Architect / Founder @ Stratik.co
**Focus:** Production-Grade AI, Cost Governance, Deterministic Orchestration.

This repository shows the engineering standards I used to build **Stratik.co** (B2B SaaS) from 0-to-1. It highlights how I solve core business challenges like: cost control, reliability, and auditability using technical architecture.

---

### 1. Infrastructure & Cost Governance
**File:** [gcp_postgres_governor.py](src/1_infrastructure/gcp_postgres_governor.py)

**Business Problem:** Uncontrolled cloud costs and database instability in a scaling SaaS environment.
**Solution:** An autonomous governor for Cloud SQL (PostgreSQL) running on GCP.

*   **Logic:** Proactively monitors `pg_stat_activity` to terminate resource-intensive queries before they impact SLA.
*   **Impact:** Reduced cloud infrastructure costs by **~30%** and eliminated downtime caused by connection pool exhaustion.
*   **Tech:** Python, Asyncpg, GCP Monitoring API.

---

### 2. Backend: Deterministic AI Orchestration
**File:**  - [backend_workflow_example.py](src/2_backend/backend_workflow_example.py)

**Business Problem:** Non-deterministic nature of LLMs poses a compliance and stability risk in B2B workflows.
**Solution:** A strict State Machine architecture enforced via Python decorators.

*   **Logic:** The `@require_valid_campaign` decorator (see `tests/`) enforces rigid state transitions. This ensures that while AI content is probabilistic, the business workflow remains 100% deterministic and auditable.
*   **Testing:** Unit tests (Pytest) verify state integrity and error handling without external dependencies.
*   **Tech:** Python 3.12, FastAPI, SQLAlchemy (Async), State Machine Pattern.

---

### 3. Frontend: Latency Management
**File:** - [StrategicChatView.tsx](src/3_frontend/StrategicChatView.tsx)

**Business Problem:** High latency of LLM inference degrades user trust and retention.
**Solution:** Optimistic UI patterns and robust state management.

*   **Logic:** Decouples user interactions from network request completion, providing an instantaneous feel despite background processing.
*   **Tech:** TypeScript, React, Optimistic Updates.

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

