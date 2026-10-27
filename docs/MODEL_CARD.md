# Model Card & Evaluation Provenance — Enterprise Hybrid Data Copilot

## 1. Overview & Purpose
`enterprise-hybrid-data-copilot` is a deterministic, inspectable **Python / FastAPI / SQLite / TypeScript** reference architecture that bridges structured relational KPI tables (`SQLite`) and unstructured operational governance documents (`Markdown/JSON` indexed via `SQLite FTS5` + semantic concept routing) with pre-query data-freshness gates, AST-validated read-only semantic SQL, deterministic numerical grounding verification, and SHA-256 digest-bound Human-in-the-Loop (HITL) workflow approvals.

- **Intended Use**: Reference implementation for Principal Applied AI & Analytics Engineering workflows, Build-vs-Adopt architectural evaluation, pre-query data quality gating, AST-constrained semantic SQL routing, and cryptographic HITL auditability.
- **Out-of-Scope Use**: The relational warehouse (`4` tables) and operational policy corpus (`8` documents / `16` passages) are synthetic enterprise artifacts. This repository is not a live financial reporting system or connected Snowflake/MS SQL production warehouse.

---

## 2. Cryptographic Provenance (`artifacts/copilot_benchmark.json`)
All benchmark results produced by `python -m copilot.evaluate` are bound to deterministic SHA-256 digests:

| Artifact | Scope | Verified SHA-256 Digest |
| :--- | :--- | :--- |
| **`data/benchmark/copilot_eval_cases.json`** | 40 Decision-Support Queries (14 `sql_only`, 10 `rag_only`, 10 `hybrid_multi_source`, 6 `blocked_data_quality`) | `634da082013aa0fc68e89479e9d32aa6b197d4f3fb9452f0c2c5c74363c547db` |
| **SQLite Relational Warehouse (`data/warehouse/`)** | 4 Tables (`zone_operational_kpis`, `zone_financial_kpis`, `vendor_contract_sla_ledger`, `legacy_supply_backlog_partition`) | `1d8879df130b7ab94612d60bceb587c5e3b8872dbb1661e1aee2e8ddfd2d00bc` |
| **Operational SOP Corpus (`data/documents/`)** | 8 Governance Documents / 16 Passages (`SOP-OPS-101` through `SOP-GDPR-808`) | `d6d92970e6662757aedc2231064659f5e3499d16a33f9f99d28b04d5dc981151` |

---

## 3. 40-Query Build-vs-Adopt Benchmark Results (`as_of_utc = 2026-10-27T12:00:00Z`)

| Architecture | SQL Execution Accuracy | Numerical Parity Rate | Freshness Gate Precision | Freshness Gate Recall | Routing Modality Accuracy | Est. Tokens / Query | Est. Cost / 1k Queries |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Ungoverned Prompt-to-SQL Baseline** | `0.7059` | `0.5100` | `0.0000` | `0.0000` | `0.3500` | `1850` | `$4.6250` |
| **2. Adopt Off-the-Shelf Text-Only RAG** | `0.0000` | `0.3825` | `0.0000` | `0.0000` | `0.2500` | `1420` | `$3.5500` |
| **3. Governed Hybrid Data Copilot (Ours)** | **`1.0000`** | **`1.0000`** | **`1.0000`** | **`1.0000`** | **`1.0000`** | **`310`** | **`$0.7750`** |

### Key Empirical Findings
1. **Why Off-the-Shelf Text-Only RAG Fails (`0.0000` SQL Execution Accuracy, `0.3825` Numerical Parity)**:
   - Standard document RAG retrieves unstructured SOP rules (`OPS-SLA-95`, `FIN-CAP-8PCT`), but cannot execute relational `SUM`/`AVG` aggregations or lookup live zone KPIs (`zone_operational_kpis`, `zone_financial_kpis`).
2. **Why Ungoverned Prompt-to-SQL Fails (`0.5100` Numerical Parity, `0.0000` Freshness Gate Precision)**:
   - Without a pre-query Data Quality Gate (`DQA-FRESH-24H`), naive text-to-SQL executes queries against stale partitions (`legacy_supply_backlog_partition`, `222.0` hours old vs `48.0` hour ceiling) and lacks access to unstructured policy thresholds (`FIN-CAP-8PCT`, `VND-SLA-995`) required for compliance synthesis.
3. **Why Building the Governed Hybrid Data Copilot Wins**:
   - Achieves **`1.0000` SQL Execution Accuracy**, **`1.0000` Numerical Parity Rate**, and **`1.0000` Freshness Gate Precision** while cutting token consumption by **`83.24%`** (`310` vs `1,850` tokens/query) by routing through compact AST-validated SQL templates instead of stuffing raw database DDL into every prompt.
