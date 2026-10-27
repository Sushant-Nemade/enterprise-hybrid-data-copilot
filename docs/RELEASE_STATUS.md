# Release Status & Operational Scope Boundaries

## Release Identification
- **Project**: `enterprise-hybrid-data-copilot`
- **Version**: `0.1.0` (`v0.1.0-reference`)
- **Date**: `2026-10-27`
- **License**: MIT

---

## 1. Verified Local Capabilities (CI & Container Tested)

| Capability | Module Owner | Verification Evidence |
| :--- | :--- | :--- |
| **Pre-Query Data Freshness & Contract Gate** | `src/copilot/data_quality.py` | Inspects SQLite schema columns (`PRAGMA table_info`), row-count bounds, column null ratios (`<= 0.05`), and timestamp age (`staleness_hours`). Blocks `legacy_supply_backlog_partition` (`222.0h > 48.0h`) with `1.0000` precision (`tests/test_data_quality_and_router.py`). |
| **Constrained Semantic SQL + Unstructured RAG Router** | `src/copilot/router.py` | Routes across `sql_only`, `rag_only`, `hybrid_multi_source`, and `blocked_data_quality`; AST-validates all SQL (`validate_sql_ast_read_only`) blocking `DROP`/`UPDATE`/`DELETE`/`PRAGMA`/comments/semicolons across 7 parametrized security tests. |
| **Deterministic Numerical Grounding Guardrail** | `src/copilot/verifier.py` | Extracts numeric, currency (`EUR`), and percentage (`%`) tokens from drafted summaries and verifies exact parity against SQL result cells and retrieved SOP passages (`tests/test_verifier_workflow_and_api.py`). |
| **Digest-Bound HITL Approval State Machine** | `src/copilot/workflow.py` | Enforces `DRAFT -> PENDING_APPROVAL -> APPROVED / REJECTED` in SQLite with append-only audit logs and automatic transition to `REJECTED` (`invalidated_by_data_drift`) when SQL snapshot or passage SHA-256 digests change. |
| **Build-vs-Adopt 40-Query Evaluation Harness** | `src/copilot/evaluate.py` | Deterministic CLI (`python -m copilot.evaluate --check`) verifying `artifacts/copilot_benchmark.json`. |
| **FastAPI Service & Decision-Support Review Console** | `src/copilot/api.py`, `src/copilot/site/index.html` | Typed Pydantic v2 endpoints and interactive 4-tab console verified on desktop and mobile. |

---

## 2. Unconfigured External Connectors & Boundaries
- **Cloud Data Warehouses (Snowflake / MS SQL Server / BigQuery / Databricks)**: **Not connected**. The reference implementation uses an embedded, deterministic SQLite warehouse seeded from `src/copilot/datasets.py` so all 40 benchmark cases and CI checks run offline with zero cloud credentials.
- **External Paid LLM APIs (Azure OpenAI / OpenAI / Anthropic)**: **Not activated**. SQL template routing and grounded synthesis execute deterministically with zero external API keys or token spend.
- **Enterprise Workflow Buses (Power Automate / ServiceNow / Jira Webhooks)**: **Not connected**. The HITL state machine is persisted in local transactional SQLite (`hitl_workflows` table) and exposed via REST endpoints (`/api/workflows/*`).
