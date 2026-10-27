# Enterprise Hybrid Data Copilot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11 | 3.12 | 3.13](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)

An inspectable **Python / FastAPI / SQLite / TypeScript** reference system that bridges **structured relational KPIs (SQLite)** and **unstructured operational documents (Markdown/JSON)** with **automated pre-query data-freshness gates**, **AST-validated read-only semantic SQL templates**, **deterministic numerical grounding verification**, and **SHA-256 digest-bound Human-in-the-Loop (HITL) workflow approvals**.

## Live Public Decision-Support Console & Documentation
- **Interactive Decision-Support Review Console (GitHub Pages)**: [https://sushant-nemade.github.io/enterprise-hybrid-data-copilot/](https://sushant-nemade.github.io/enterprise-hybrid-data-copilot/)
  - *Explore the 40-query Build-vs-Adopt benchmark, inspect AST-validated read-only SQL plans alongside retrieved SOP passages and token-by-token numerical parity checks, simulate stale warehouse partition blocking, and step through the `DRAFT -> PENDING_APPROVAL -> APPROVED / REJECTED` HITL state machine directly in your browser.*
- **Architecture Deep Dive**: [docs/ARCHITECTURE_DEEP_DIVE.md](docs/ARCHITECTURE_DEEP_DIVE.md)
- **Model Card & Evaluation Provenance**: [docs/MODEL_CARD.md](docs/MODEL_CARD.md)
- **Release Status & Operational Boundaries**: [docs/RELEASE_STATUS.md](docs/RELEASE_STATUS.md)
- **Machine-Readable Benchmark Artifact**: [artifacts/copilot_benchmark.json](artifacts/copilot_benchmark.json)

---

## 1. Verified 40-Query Build-vs-Adopt Benchmark (`artifacts/copilot_benchmark.json`)

Evaluated deterministically across 40 operational & financial decision-support queries (`dataset_sha256: 634da082013aa0fc68e89479e9d32aa6b197d4f3fb9452f0c2c5c74363c547db`), 4 relational KPI tables (`database_sha256: 1d8879df130b7ab94612d60bceb587c5e3b8872dbb1661e1aee2e8ddfd2d00bc`), and 16 operational SOP passages (`corpus_sha256: d6d92970e6662757aedc2231064659f5e3499d16a33f9f99d28b04d5dc981151`):

| Architecture | SQL Execution Accuracy | Numerical Parity Rate | Freshness Gate Precision | Routing Accuracy | Est. Tokens / Query | Est. Cost / 1k Queries |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Ungoverned Prompt-to-SQL Baseline** | `0.7059` | `0.5100` | `0.0000` | `0.3500` | `1850` | `$4.6250` |
| **2. Adopt Off-the-Shelf Text-Only RAG** | `0.0000` | `0.3825` | `0.0000` | `0.2500` | `1420` | `$3.5500` |
| **3. Governed Hybrid Data Copilot (Ours)** | **`1.0000`** | **`1.0000`** | **`1.0000`** | **`1.0000`** | **`310`** | **`$0.7750`** |

- **Key Benchmark Highlights**:
  - **SQL Execution Accuracy**: **`1.0000`** (`+0.2941` over Ungoverned Prompt-to-SQL, which executes against stale partitions and fails on unstructured SOP queries; `+1.0000` over Text-Only RAG).
  - **Numerical Parity Rate**: **`1.0000`** (`+0.4900` over Prompt-to-SQL and `+0.6175` over Text-Only RAG—every number, currency figure, and percentage in drafted summaries is verified against exact SQL cells and SOP thresholds).
  - **Freshness Gate Precision**: **`1.0000`** (blocks 6/6 queries targeting stale partitions like `legacy_supply_backlog_partition` at `222.0h > 48.0h` SLA).
  - **Token Cost Reduction**: **`-83.24%`** (`310` vs `1,850` tokens/query) via constrained semantic SQL template routing.

---

## 2. Core Engineering Modules

1. **Data Freshness & Quality Gate ([src/copilot/data_quality.py](src/copilot/data_quality.py))**:
   - Inspects relational tables before any analytics or RAG execution for schema contracts (`PRAGMA table_info`), row-count bounds, column null ratios (`<= 5.0%`), and refresh timestamp freshness (`refreshed_at_utc` vs `max_staleness_hours`).
   - Emits a structured `DataReadinessReport` and blocks queries targeting stale or contract-violating partitions.
2. **Constrained Semantic SQL + Unstructured RAG Router ([src/copilot/router.py](src/copilot/router.py))**:
   - Routes stakeholder questions across `sql_only`, `rag_only`, `hybrid_multi_source`, and `blocked_data_quality`.
   - Enforces read-only AST/lexical SQL validation (`validate_sql_ast_read_only`) blocking `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `ATTACH`, `PRAGMA`, SQL comments, and multi-statement semicolons.
3. **Deterministic Numerical Grounding Guardrail ([src/copilot/verifier.py](src/copilot/verifier.py))**:
   - Extracts every numeric, currency (`EUR`), and percentage (`%`) token in the drafted summary and verifies exact mathematical parity against the SQL result set and retrieved SOP passages.
4. **Human-in-the-Loop (HITL) Approval & Audit Trail ([src/copilot/workflow.py](src/copilot/workflow.py))**:
   - Implements a transactional SQLite approval state machine (`DRAFT -> PENDING_APPROVAL -> APPROVED / REJECTED`) with append-only audit logs.
   - Binds approvals to $\text{SHA-256}(\text{question} \parallel \text{sql\_snapshot\_sha256} \parallel \text{sorted\_passage\_sha256s} \parallel \text{answer\_sha256})$, automatically invalidating `APPROVED` records to `REJECTED` (`invalidated_by_data_drift`) when underlying SQL data or policy passages change.
5. **Build-vs-Adopt Evaluation Harness ([src/copilot/evaluate.py](src/copilot/evaluate.py))**:
   - Benchmarks all 40 operational & financial decision-support queries across 3 architectures and outputs [artifacts/copilot_benchmark.json](artifacts/copilot_benchmark.json).

---

## 3. Repository Structure

```text
├── .github/workflows/
│   ├── ci.yml                      # Ubuntu (3.12, 3.13), Windows (3.13), ruff, mypy, pytest, evaluate --check, pip-audit, Docker
│   └── pages.yml                   # Automated GitHub Pages deployment of the Decision-Support Review Console
├── data/
│   ├── warehouse/                  # 4 relational KPI tables and declarative schema/freshness contracts
│   ├── documents/                  # 8 operational SOP, financial, vendor SLA, and GDPR governance documents (16 passages)
│   └── benchmark/                  # 40 labelled decision-support benchmark queries (copilot_eval_cases.json)
├── frontend/
│   ├── tsconfig.json               # Strict TypeScript configuration
│   └── src/console.ts              # Typed interfaces for the Decision-Support Review Console
├── src/copilot/
│   ├── schemas.py                  # Strict Pydantic v2 data contracts
│   ├── datasets.py                 # Canonical SQLite warehouse seeder, SOP passages, and 40 benchmark cases
│   ├── data_quality.py             # Pre-query Data Freshness & Quality Gate (DataReadinessReport)
│   ├── router.py                   # AST-validated read-only SQL + Hybrid SOP RAG Router
│   ├── verifier.py                 # Deterministic Numerical Grounding Guardrail
│   ├── workflow.py                 # Digest-Bound HITL Approval State Machine (DRAFT -> PENDING_APPROVAL -> APPROVED/REJECTED)
│   ├── evaluate.py                 # 40-query Build-vs-Adopt CLI evaluation harness
│   ├── api.py                      # FastAPI service and OpenAPI endpoints
│   └── site/                       # Interactive Decision-Support Review Console (served at / and deployed to GitHub Pages)
├── artifacts/
│   └── copilot_benchmark.json      # Machine-readable Build-vs-Adopt benchmark report with SHA-256 provenance
├── docs/
│   ├── ARCHITECTURE_DEEP_DIVE.md
│   ├── MODEL_CARD.md
│   └── RELEASE_STATUS.md
├── scripts/
│   └── package_site.py             # Packages verified benchmark and scenario bundles into src/copilot/site/data/
├── tests/                          # Pytest suite covering freshness gates, AST SQL safety, numerical parity, HITL, and FastAPI
├── Dockerfile                      # Non-root Python 3.13 container image
└── pyproject.toml
```

---

## 4. Local Quickstart & Verification

```bash
# 1. Install locked dependencies
uv sync --frozen

# 2. Verify the 40-query Build-vs-Adopt benchmark against the committed artifact
uv run --frozen python -m copilot.evaluate --check

# 3. Run ruff, strict mypy, and pytest
uv run --frozen ruff check src tests scripts
uv run --frozen mypy src/copilot
uv run --frozen pytest -v

# 4. Launch the FastAPI server + Decision-Support Review Console at http://127.0.0.1:8000/
uv run --frozen uvicorn copilot.api:app --host 127.0.0.1 --port 8000
```
