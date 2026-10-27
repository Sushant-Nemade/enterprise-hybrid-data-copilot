"""Canonical relational KPI tables, unstructured operational SOPs, and 40-query benchmark dataset."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from copilot.schemas import (
    CopilotEvalCase,
    CopilotEvalDatasetFile,
    OperationalPassage,
    RouteModality,
    TableContract,
)


def sha256_hex(data: str | bytes) -> str:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(payload).hexdigest()


def get_table_contracts() -> list[TableContract]:
    """Return declarative freshness, row-count, null-ratio, and schema contracts for all 4 tables."""
    return [
        TableContract(
            table_name="zone_operational_kpis",
            description="Quarterly operational throughput, SLA breaches, OTD %, MTTR, and automation coverage by zone.",
            required_columns=[
                "zone_id",
                "fiscal_quarter",
                "units_shipped",
                "sla_breach_count",
                "on_time_delivery_pct",
                "mean_repair_hours",
                "automation_coverage_pct",
                "refreshed_at_utc",
            ],
            timestamp_column="refreshed_at_utc",
            min_rows=4,
            max_rows=100,
            max_null_ratio=0.05,
            warn_staleness_hours=12.0,
            max_staleness_hours=24.0,
        ),
        TableContract(
            table_name="zone_financial_kpis",
            description="Quarterly revenue, OPEX budget vs actual, variance %, gross margin %, and AI spend by zone.",
            required_columns=[
                "zone_id",
                "fiscal_quarter",
                "revenue_eur",
                "opex_budget_eur",
                "actual_opex_eur",
                "opex_variance_pct",
                "gross_margin_pct",
                "cloud_ai_spend_eur",
                "refreshed_at_utc",
            ],
            timestamp_column="refreshed_at_utc",
            min_rows=4,
            max_rows=100,
            max_null_ratio=0.05,
            warn_staleness_hours=12.0,
            max_staleness_hours=24.0,
        ),
        TableContract(
            table_name="vendor_contract_sla_ledger",
            description="Tier-1 vendor contract values, uptime %, critical incidents, and SLA penalty rebates.",
            required_columns=[
                "vendor_id",
                "vendor_name",
                "zone_id",
                "annual_contract_eur",
                "uptime_pct",
                "critical_incidents_q3",
                "penalty_rebate_eur",
                "refreshed_at_utc",
            ],
            timestamp_column="refreshed_at_utc",
            min_rows=5,
            max_rows=200,
            max_null_ratio=0.05,
            warn_staleness_hours=12.0,
            max_staleness_hours=24.0,
        ),
        TableContract(
            table_name="legacy_supply_backlog_partition",
            description="Legacy warehouse component backlog feed (intentionally stale partition for gate testing).",
            required_columns=[
                "partition_id",
                "zone_id",
                "backordered_skus",
                "blocked_orders_eur",
                "refreshed_at_utc",
            ],
            timestamp_column="refreshed_at_utc",
            min_rows=4,
            max_rows=100,
            max_null_ratio=0.05,
            warn_staleness_hours=24.0,
            max_staleness_hours=48.0,
        ),
    ]


ZONE_OPERATIONAL_ROWS: list[dict[str, Any]] = [
    {
        "zone_id": "Zone_DACH_Diagnostics",
        "fiscal_quarter": "2026-Q3",
        "units_shipped": 1850,
        "sla_breach_count": 1,
        "on_time_delivery_pct": 98.4,
        "mean_repair_hours": 3.2,
        "automation_coverage_pct": 88.5,
        "refreshed_at_utc": "2026-10-27T09:00:00Z",
    },
    {
        "zone_id": "Zone_EMEA_Imaging",
        "fiscal_quarter": "2026-Q3",
        "units_shipped": 1420,
        "sla_breach_count": 3,
        "on_time_delivery_pct": 96.8,
        "mean_repair_hours": 4.5,
        "automation_coverage_pct": 82.0,
        "refreshed_at_utc": "2026-10-27T09:00:00Z",
    },
    {
        "zone_id": "Zone_US_East_Robotics",
        "fiscal_quarter": "2026-Q3",
        "units_shipped": 1120,
        "sla_breach_count": 9,
        "on_time_delivery_pct": 91.2,
        "mean_repair_hours": 7.8,
        "automation_coverage_pct": 71.4,
        "refreshed_at_utc": "2026-10-27T09:00:00Z",
    },
    {
        "zone_id": "Zone_APAC_LabSystems",
        "fiscal_quarter": "2026-Q3",
        "units_shipped": 1610,
        "sla_breach_count": 2,
        "on_time_delivery_pct": 97.1,
        "mean_repair_hours": 3.9,
        "automation_coverage_pct": 84.2,
        "refreshed_at_utc": "2026-10-27T09:00:00Z",
    },
]

ZONE_FINANCIAL_ROWS: list[dict[str, Any]] = [
    {
        "zone_id": "Zone_DACH_Diagnostics",
        "fiscal_quarter": "2026-Q3",
        "revenue_eur": 18900000.0,
        "opex_budget_eur": 4100000.0,
        "actual_opex_eur": 3980000.0,
        "opex_variance_pct": -2.93,
        "gross_margin_pct": 64.2,
        "cloud_ai_spend_eur": 145000.0,
        "refreshed_at_utc": "2026-10-27T09:30:00Z",
    },
    {
        "zone_id": "Zone_EMEA_Imaging",
        "fiscal_quarter": "2026-Q3",
        "revenue_eur": 14250000.0,
        "opex_budget_eur": 3200000.0,
        "actual_opex_eur": 3344000.0,
        "opex_variance_pct": 4.5,
        "gross_margin_pct": 61.5,
        "cloud_ai_spend_eur": 118000.0,
        "refreshed_at_utc": "2026-10-27T09:30:00Z",
    },
    {
        "zone_id": "Zone_US_East_Robotics",
        "fiscal_quarter": "2026-Q3",
        "revenue_eur": 11600000.0,
        "opex_budget_eur": 2800000.0,
        "actual_opex_eur": 3192000.0,
        "opex_variance_pct": 14.0,
        "gross_margin_pct": 54.8,
        "cloud_ai_spend_eur": 210000.0,
        "refreshed_at_utc": "2026-10-27T09:30:00Z",
    },
    {
        "zone_id": "Zone_APAC_LabSystems",
        "fiscal_quarter": "2026-Q3",
        "revenue_eur": 15450000.0,
        "opex_budget_eur": 3500000.0,
        "actual_opex_eur": 3570000.0,
        "opex_variance_pct": 2.0,
        "gross_margin_pct": 62.0,
        "cloud_ai_spend_eur": 132000.0,
        "refreshed_at_utc": "2026-10-27T09:30:00Z",
    },
]

VENDOR_SLA_ROWS: list[dict[str, Any]] = [
    {
        "vendor_id": "VND-CLOUD-01",
        "vendor_name": "SovereignCloud Frankfurt GmbH",
        "zone_id": "Zone_DACH_Diagnostics",
        "annual_contract_eur": 480000.0,
        "uptime_pct": 99.96,
        "critical_incidents_q3": 0,
        "penalty_rebate_eur": 0.0,
        "refreshed_at_utc": "2026-10-27T08:00:00Z",
    },
    {
        "vendor_id": "VND-MED-02",
        "vendor_name": "EuroOptics Cryo Components AG",
        "zone_id": "Zone_EMEA_Imaging",
        "annual_contract_eur": 620000.0,
        "uptime_pct": 99.45,
        "critical_incidents_q3": 1,
        "penalty_rebate_eur": 31000.0,
        "refreshed_at_utc": "2026-10-27T08:00:00Z",
    },
    {
        "vendor_id": "VND-LOG-03",
        "vendor_name": "Atlantic Precision Servo Corp",
        "zone_id": "Zone_US_East_Robotics",
        "annual_contract_eur": 540000.0,
        "uptime_pct": 98.2,
        "critical_incidents_q3": 4,
        "penalty_rebate_eur": 64800.0,
        "refreshed_at_utc": "2026-10-27T08:00:00Z",
    },
    {
        "vendor_id": "VND-SEC-04",
        "vendor_name": "Nordic Telemetry Guard AB",
        "zone_id": "Zone_DACH_Diagnostics",
        "annual_contract_eur": 290000.0,
        "uptime_pct": 99.92,
        "critical_incidents_q3": 0,
        "penalty_rebate_eur": 0.0,
        "refreshed_at_utc": "2026-10-27T08:00:00Z",
    },
    {
        "vendor_id": "VND-DATA-05",
        "vendor_name": "Pacific Lab Automation Pte Ltd",
        "zone_id": "Zone_APAC_LabSystems",
        "annual_contract_eur": 410000.0,
        "uptime_pct": 99.6,
        "critical_incidents_q3": 1,
        "penalty_rebate_eur": 0.0,
        "refreshed_at_utc": "2026-10-27T08:00:00Z",
    },
]

LEGACY_STALE_BACKLOG_ROWS: list[dict[str, Any]] = [
    {
        "partition_id": "PART-2026-W41-DACH",
        "zone_id": "Zone_DACH_Diagnostics",
        "backordered_skus": 14,
        "blocked_orders_eur": 320000.0,
        "refreshed_at_utc": "2026-10-18T06:00:00Z",
    },
    {
        "partition_id": "PART-2026-W41-EMEA",
        "zone_id": "Zone_EMEA_Imaging",
        "backordered_skus": 27,
        "blocked_orders_eur": 610000.0,
        "refreshed_at_utc": "2026-10-18T06:00:00Z",
    },
    {
        "partition_id": "PART-2026-W41-USEAST",
        "zone_id": "Zone_US_East_Robotics",
        "backordered_skus": 53,
        "blocked_orders_eur": 1240000.0,
        "refreshed_at_utc": "2026-10-18T06:00:00Z",
    },
    {
        "partition_id": "PART-2026-W41-APAC",
        "zone_id": "Zone_APAC_LabSystems",
        "backordered_skus": 19,
        "blocked_orders_eur": 440000.0,
        "refreshed_at_utc": "2026-10-18T06:00:00Z",
    },
]


def seed_sqlite_warehouse(conn: sqlite3.Connection) -> None:
    """Populate the 4 enterprise relational KPI tables deterministically in SQLite."""
    with conn:
        conn.execute("DROP TABLE IF EXISTS zone_operational_kpis;")
        conn.execute(
            """
            CREATE TABLE zone_operational_kpis (
                zone_id TEXT PRIMARY KEY,
                fiscal_quarter TEXT NOT NULL,
                units_shipped INTEGER NOT NULL,
                sla_breach_count INTEGER NOT NULL,
                on_time_delivery_pct REAL NOT NULL,
                mean_repair_hours REAL NOT NULL,
                automation_coverage_pct REAL NOT NULL,
                refreshed_at_utc TEXT NOT NULL
            );
            """
        )
        for r in ZONE_OPERATIONAL_ROWS:
            conn.execute(
                """
                INSERT INTO zone_operational_kpis VALUES (
                    :zone_id, :fiscal_quarter, :units_shipped, :sla_breach_count,
                    :on_time_delivery_pct, :mean_repair_hours, :automation_coverage_pct, :refreshed_at_utc
                );
                """,
                r,
            )

        conn.execute("DROP TABLE IF EXISTS zone_financial_kpis;")
        conn.execute(
            """
            CREATE TABLE zone_financial_kpis (
                zone_id TEXT PRIMARY KEY,
                fiscal_quarter TEXT NOT NULL,
                revenue_eur REAL NOT NULL,
                opex_budget_eur REAL NOT NULL,
                actual_opex_eur REAL NOT NULL,
                opex_variance_pct REAL NOT NULL,
                gross_margin_pct REAL NOT NULL,
                cloud_ai_spend_eur REAL NOT NULL,
                refreshed_at_utc TEXT NOT NULL
            );
            """
        )
        for r in ZONE_FINANCIAL_ROWS:
            conn.execute(
                """
                INSERT INTO zone_financial_kpis VALUES (
                    :zone_id, :fiscal_quarter, :revenue_eur, :opex_budget_eur,
                    :actual_opex_eur, :opex_variance_pct, :gross_margin_pct,
                    :cloud_ai_spend_eur, :refreshed_at_utc
                );
                """,
                r,
            )

        conn.execute("DROP TABLE IF EXISTS vendor_contract_sla_ledger;")
        conn.execute(
            """
            CREATE TABLE vendor_contract_sla_ledger (
                vendor_id TEXT PRIMARY KEY,
                vendor_name TEXT NOT NULL,
                zone_id TEXT NOT NULL,
                annual_contract_eur REAL NOT NULL,
                uptime_pct REAL NOT NULL,
                critical_incidents_q3 INTEGER NOT NULL,
                penalty_rebate_eur REAL NOT NULL,
                refreshed_at_utc TEXT NOT NULL
            );
            """
        )
        for r in VENDOR_SLA_ROWS:
            conn.execute(
                """
                INSERT INTO vendor_contract_sla_ledger VALUES (
                    :vendor_id, :vendor_name, :zone_id, :annual_contract_eur,
                    :uptime_pct, :critical_incidents_q3, :penalty_rebate_eur, :refreshed_at_utc
                );
                """,
                r,
            )

        conn.execute("DROP TABLE IF EXISTS legacy_supply_backlog_partition;")
        conn.execute(
            """
            CREATE TABLE legacy_supply_backlog_partition (
                partition_id TEXT PRIMARY KEY,
                zone_id TEXT NOT NULL,
                backordered_skus INTEGER NOT NULL,
                blocked_orders_eur REAL NOT NULL,
                refreshed_at_utc TEXT NOT NULL
            );
            """
        )
        for r in LEGACY_STALE_BACKLOG_ROWS:
            conn.execute(
                """
                INSERT INTO legacy_supply_backlog_partition VALUES (
                    :partition_id, :zone_id, :backordered_skus, :blocked_orders_eur, :refreshed_at_utc
                );
                """,
                r,
            )


def get_operational_passages() -> list[OperationalPassage]:
    """Return 16 unstructured operational SOP, procurement, and governance passages across 8 documents."""
    raw_defs = [
        (
            "SOP-OPS-101#S1",
            "SOP-OPS-101",
            "Zone On-Time Delivery SLA & Escalation Thresholds",
            "operations_governance",
            "1. Minimum On-Time Delivery Target & Breach Cap (OPS-SLA-95)",
            "2026-08-01",
            (
                "Under Operational Policy OPS-SLA-95, every manufacturing and clinical zone must maintain "
                "a minimum quarterly On-Time Delivery (OTD) rate of 95.0% and no more than 5 quarterly "
                "SLA breaches. Any zone falling below 95.0% OTD or exceeding 5 SLA breaches is classified "
                "as Red-Tier Non-Compliant and must submit a Root-Cause Corrective Action Plan (CAPA) "
                "within 5 business days."
            ),
        ),
        (
            "SOP-OPS-101#S2",
            "SOP-OPS-101",
            "Zone On-Time Delivery SLA & Escalation Thresholds",
            "operations_governance",
            "2. Mean Time To Repair (MTTR) Ceiling & Automation Target (OPS-MTTR-6H)",
            "2026-08-01",
            (
                "Control OPS-MTTR-6H establishes a maximum Mean Time To Repair (mean_repair_hours) ceiling "
                "of 6.0 hours for automated diagnostic and robotics lines, alongside a target workflow "
                "automation coverage of at least 80.0%. Zones exceeding 6.0 repair hours require an "
                "immediate field-engineering dispatch audit."
            ),
        ),
        (
            "SOP-FIN-202#S1",
            "SOP-FIN-202",
            "Quarterly OPEX Variance Cap & CFO Freeze Protocol",
            "financial_governance",
            "1. OPEX Variance Thresholds & Discretionary Spend Freeze (FIN-CAP-8PCT)",
            "2026-08-15",
            (
                "Under Financial Governance Policy FIN-CAP-8PCT, any operating zone whose quarterly OPEX "
                "variance (opex_variance_pct) exceeds 8.0% above budget triggers a mandatory CFO "
                "Discretionary Spend Freeze and requires Human-in-the-Loop (HITL) executive approval "
                "before releasing new contractor or cloud compute requisitions. Variances between 3.0% "
                "and 8.0% require a VP Finance variance memo."
            ),
        ),
        (
            "SOP-FIN-202#S2",
            "SOP-FIN-202",
            "Quarterly OPEX Variance Cap & CFO Freeze Protocol",
            "financial_governance",
            "2. Minimum Gross Margin & Cloud AI Spend Allocation (FIN-GM-58)",
            "2026-08-15",
            (
                "Directive FIN-GM-58 requires operating zones to sustain a minimum quarterly gross margin "
                "of 58.0% and caps quarterly cloud AI inference and training expenditure at EUR 180,000 "
                "per zone unless a high-volume workload waiver is countersigned."
            ),
        ),
        (
            "SOP-VND-303#S1",
            "SOP-VND-303",
            "Tier-1 Supplier Uptime SLA & Penalty Rebate Schedule",
            "vendor_procurement",
            "1. Minimum 99.5% Supplier Uptime & Penalty Tiers (VND-SLA-995)",
            "2026-07-20",
            (
                "Clause VND-SLA-995 mandates a minimum 99.5% quarterly availability (uptime_pct) across "
                "all Tier-1 production suppliers. Suppliers recording uptime between 99.0% and 99.49% "
                "incur a 5.0% annual contract penalty rebate. Suppliers falling below 99.0% uptime or "
                "recording 3 or more critical incidents in a quarter incur a 12.0% annual contract "
                "penalty rebate and formal vendor probation."
            ),
        ),
        (
            "SOP-VND-303#S2",
            "SOP-VND-303",
            "Tier-1 Supplier Uptime SLA & Penalty Rebate Schedule",
            "vendor_procurement",
            "2. Executive Procurement Board Review Threshold (VND-BOARD-500K)",
            "2026-07-20",
            (
                "Under Schedule VND-BOARD-500K, any Tier-1 supplier contract with an annual contract "
                "value (annual_contract_eur) of EUR 500,000 or higher requires semi-annual resilience "
                "auditing and dual sign-off from the VP of Procurement and Chief Information Security Officer."
            ),
        ),
        (
            "SOP-DQA-404#S1",
            "SOP-DQA-404",
            "Relational Data Warehouse Freshness & Null-Ratio Gate",
            "data_quality",
            "1. Pre-Query Freshness SLA & Stale Partition Blocking (DQA-FRESH-24H)",
            "2026-09-01",
            (
                "Standard DQA-FRESH-24H requires the Data Quality Gate to inspect table refresh timestamps "
                "(refreshed_at_utc) prior to executing any SQL analytics or hybrid RAG synthesis. Operational "
                "and financial KPI tables have a warning threshold of 12.0 hours and a hard blocking ceiling "
                "of 24.0 hours; legacy supply backlog partitions have a hard blocking ceiling of 48.0 hours. "
                "Any query targeting a table in blocked_stale status must be rejected before SQL execution."
            ),
        ),
        (
            "SOP-DQA-404#S2",
            "SOP-DQA-404",
            "Relational Data Warehouse Freshness & Null-Ratio Gate",
            "data_quality",
            "2. Schema Contract & Column Null-Ratio Bounds (DQA-NULL-5PCT)",
            "2026-09-01",
            (
                "Control DQA-NULL-5PCT enforces strict relational schema contracts: every required column "
                "must exist, table row counts must fall within [min_rows, max_rows], and the maximum "
                "observed column null ratio must not exceed 5.0% (0.05). Violations transition the table "
                "to blocked_contract status."
            ),
        ),
        (
            "SOP-SQL-505#S1",
            "SOP-SQL-505",
            "Read-Only Parameterized SQL & AST Security Policy",
            "sql_security",
            "1. AST Read-Only Validation & Mutating Keyword Ban (SQL-AST-RO)",
            "2026-09-10",
            (
                "Security Policy SQL-AST-RO prohibits unconstrained free-text LLM SQL execution. Every "
                "generated query must map to an approved parameterized SELECT template, bind arguments "
                "exclusively via SQLite parameter placeholders (:param), and pass AST token inspection "
                "blocking INSERT, UPDATE, DELETE, DROP, ALTER, ATTACH, PRAGMA, and multi-statement semicolons."
            ),
        ),
        (
            "SOP-SQL-505#S2",
            "SOP-SQL-505",
            "Read-Only Parameterized SQL & AST Security Policy",
            "sql_security",
            "2. Deterministic Numerical Grounding Guardrail (NUM-PARITY-100)",
            "2026-09-10",
            (
                "Under Control NUM-PARITY-100, every numeric, currency, or percentage token present in "
                "a drafted executive summary must be extracted and verified against the exact SQL result "
                "set or retrieved policy passage within a relative tolerance of 1e-2 (0.01). Any unverified "
                "number blocks automatic release."
            ),
        ),
        (
            "SOP-HITL-606#S1",
            "SOP-HITL-606",
            "Digest-Bound Executive Sign-Off & Snapshot Invalidation",
            "hitl_governance",
            "1. Four-State Approval Lifecycle (HITL-STATE-4)",
            "2026-09-15",
            (
                "Standard HITL-STATE-4 governs decision-support briefs through a deterministic state "
                "machine: DRAFT -> PENDING_APPROVAL -> APPROVED or REJECTED. Transitions are logged in "
                "an append-only SQLite audit trail with actor identity, UTC timestamp, and bound SHA-256 "
                "evidence digest."
            ),
        ),
        (
            "SOP-HITL-606#S2",
            "SOP-HITL-606",
            "Digest-Bound Executive Sign-Off & Snapshot Invalidation",
            "hitl_governance",
            "2. Composite Evidence SHA-256 Binding & Drift Invalidation (HITL-DRIFT-SHA)",
            "2026-09-15",
            (
                "Control HITL-DRIFT-SHA binds every human approval to SHA256(normalized_question || "
                "sql_snapshot_sha256 || sorted_passage_sha256s || answer_sha256). If an underlying SQL "
                "table refresh or SOP revision changes the snapshot hash, digest verification automatically "
                "transitions the workflow from APPROVED to REJECTED with reason invalidated_by_data_drift."
            ),
        ),
        (
            "SOP-AI-707#S1",
            "SOP-AI-707",
            "Build-vs-Adopt Decision Matrix for Enterprise AI Systems",
            "architecture_strategy",
            "1. When to Adopt Commodity SaaS vs Build Governed Hybrid Copilot (ARCH-BVA-01)",
            "2026-09-20",
            (
                "Framework ARCH-BVA-01 establishes the enterprise Build-vs-Adopt rule: commodity document "
                "search with non-financial data should adopt off-the-shelf SaaS assistants, whereas workflows "
                "combining regulated relational KPIs, strict numerical parity (100% grounding), pre-query "
                "data freshness gates, and cryptographic HITL audit trails require building a governed "
                "hybrid semantic layer."
            ),
        ),
        (
            "SOP-AI-707#S2",
            "SOP-AI-707",
            "Build-vs-Adopt Decision Matrix for Enterprise AI Systems",
            "architecture_strategy",
            "2. Token Cost & Latency Efficiency Targets (ARCH-COST-20MS)",
            "2026-09-20",
            (
                "Target ARCH-COST-20MS specifies that deterministic template-routed SQL and local hybrid "
                "retrieval must execute in under 25 milliseconds on CPU while reducing external LLM token "
                "consumption by at least 75.0% compared to unconstrained schema-stuffing prompt-to-SQL agents."
            ),
        ),
        (
            "SOP-GDPR-808#S1",
            "SOP-GDPR-808",
            "Cross-Region Telemetry Retention & Anonymization Standard",
            "privacy_gdpr",
            "1. Sovereign EU Warehouse Residency & 90-Day Audit Retention (GDPR-WH-90D)",
            "2026-07-15",
            (
                "Under Policy GDPR-WH-90D, all European operational and financial warehouse snapshots must "
                "reside in eu-central-1 (Frankfurt) with query audit logs retained for 90 calendar days "
                "and employee operator identifiers pseudonymized before analytics export."
            ),
        ),
        (
            "SOP-GDPR-808#S2",
            "SOP-GDPR-808",
            "Cross-Region Telemetry Retention & Anonymization Standard",
            "privacy_gdpr",
            "2. Right to Erasure & Snapshot Purge SLA (GDPR-PURGE-14D)",
            "2026-07-15",
            (
                "Control GDPR-PURGE-14D requires purging revoked personal identifiers across relational "
                "tables, FTS5 search indices, and cached workflow snapshots within 14 calendar days of a "
                "verified GDPR Article 17 request."
            ),
        ),
    ]

    passages: list[OperationalPassage] = []
    for pid, did, title, cat, heading, eff_date, text in raw_defs:
        digest = sha256_hex(f"{pid}|{did}|{title}|{heading}|{eff_date}|{text}")
        passages.append(
            OperationalPassage(
                passage_id=pid,
                doc_id=did,
                title=title,
                category=cat,
                section_heading=heading,
                effective_date=eff_date,
                text=text,
                sha256_digest=digest,
            )
        )
    return passages


def get_40_eval_cases() -> list[CopilotEvalCase]:
    """Return the 40 labelled operational & financial decision-support benchmark cases."""
    return [
        # =====================================================================
        # SLICE A: 14 Structured Relational SQL KPI Queries (SQL_ONLY)
        # =====================================================================
        CopilotEvalCase(
            case_id="QRY-001",
            category="sql_operational_zone",
            question="What were the units shipped, SLA breach count, and on-time delivery percentage for Zone_DACH_Diagnostics in 2026-Q3?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_ops_by_id",
            expected_target_tables=["zone_operational_kpis"],
            expected_numbers=[1850.0, 1.0, 98.4],
            reference_summary="In 2026-Q3, Zone_DACH_Diagnostics shipped 1,850 units with 1 SLA breach and 98.4% on-time delivery.",
        ),
        CopilotEvalCase(
            case_id="QRY-002",
            category="sql_operational_zone",
            question="What were the units shipped, SLA breach count, and on-time delivery percentage for Zone_EMEA_Imaging in 2026-Q3?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_ops_by_id",
            expected_target_tables=["zone_operational_kpis"],
            expected_numbers=[1420.0, 3.0, 96.8],
            reference_summary="In 2026-Q3, Zone_EMEA_Imaging shipped 1,420 units with 3 SLA breaches and 96.8% on-time delivery.",
        ),
        CopilotEvalCase(
            case_id="QRY-003",
            category="sql_operational_zone",
            question="What were the units shipped, SLA breach count, and on-time delivery percentage for Zone_US_East_Robotics in 2026-Q3?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_ops_by_id",
            expected_target_tables=["zone_operational_kpis"],
            expected_numbers=[1120.0, 9.0, 91.2],
            reference_summary="In 2026-Q3, Zone_US_East_Robotics shipped 1,120 units with 9 SLA breaches and 91.2% on-time delivery.",
        ),
        CopilotEvalCase(
            case_id="QRY-004",
            category="sql_operational_zone",
            question="What were the units shipped, SLA breach count, and on-time delivery percentage for Zone_APAC_LabSystems in 2026-Q3?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_ops_by_id",
            expected_target_tables=["zone_operational_kpis"],
            expected_numbers=[1610.0, 2.0, 97.1],
            reference_summary="In 2026-Q3, Zone_APAC_LabSystems shipped 1,610 units with 2 SLA breaches and 97.1% on-time delivery.",
        ),
        CopilotEvalCase(
            case_id="QRY-005",
            category="sql_operational_agg",
            question="What is the total units shipped, total SLA breaches, and average on-time delivery percentage across all operational zones in 2026-Q3?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_ops_summary",
            expected_target_tables=["zone_operational_kpis"],
            expected_numbers=[6000.0, 15.0, 95.88],
            reference_summary="Across all 4 zones in 2026-Q3, total units shipped were 6,000, total SLA breaches were 15, and average on-time delivery was 95.88%.",
        ),
        CopilotEvalCase(
            case_id="QRY-006",
            category="sql_financial_zone",
            question="What was the revenue, actual OPEX, OPEX variance percentage, and gross margin percentage for Zone_DACH_Diagnostics in 2026-Q3?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_fin_by_id",
            expected_target_tables=["zone_financial_kpis"],
            expected_numbers=[18900000.0, 3980000.0, -2.93, 64.2],
            reference_summary="Zone_DACH_Diagnostics recorded EUR 18,900,000 revenue, EUR 3,980,000 actual OPEX (-2.93% variance), and 64.2% gross margin.",
        ),
        CopilotEvalCase(
            case_id="QRY-007",
            category="sql_financial_zone",
            question="What was the revenue, actual OPEX, OPEX variance percentage, and gross margin percentage for Zone_EMEA_Imaging in 2026-Q3?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_fin_by_id",
            expected_target_tables=["zone_financial_kpis"],
            expected_numbers=[14250000.0, 3344000.0, 4.5, 61.5],
            reference_summary="Zone_EMEA_Imaging recorded EUR 14,250,000 revenue, EUR 3,344,000 actual OPEX (4.5% variance), and 61.5% gross margin.",
        ),
        CopilotEvalCase(
            case_id="QRY-008",
            category="sql_financial_zone",
            question="What was the revenue, actual OPEX, OPEX variance percentage, and gross margin percentage for Zone_US_East_Robotics in 2026-Q3?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_fin_by_id",
            expected_target_tables=["zone_financial_kpis"],
            expected_numbers=[11600000.0, 3192000.0, 14.0, 54.8],
            reference_summary="Zone_US_East_Robotics recorded EUR 11,600,000 revenue, EUR 3,192,000 actual OPEX (14.0% variance), and 54.8% gross margin.",
        ),
        CopilotEvalCase(
            case_id="QRY-009",
            category="sql_financial_zone",
            question="What was the revenue, actual OPEX, OPEX variance percentage, and gross margin percentage for Zone_APAC_LabSystems in 2026-Q3?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_fin_by_id",
            expected_target_tables=["zone_financial_kpis"],
            expected_numbers=[15450000.0, 3570000.0, 2.0, 62.0],
            reference_summary="Zone_APAC_LabSystems recorded EUR 15,450,000 revenue, EUR 3,570,000 actual OPEX (2.0% variance), and 62.0% gross margin.",
        ),
        CopilotEvalCase(
            case_id="QRY-010",
            category="sql_financial_agg",
            question="What is the total revenue, total actual OPEX, and total cloud AI spend in EUR across all zones in 2026-Q3?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_fin_summary",
            expected_target_tables=["zone_financial_kpis"],
            expected_numbers=[60200000.0, 14086000.0, 605000.0],
            reference_summary="Across all zones in 2026-Q3, total revenue was EUR 60,200,000, total actual OPEX was EUR 14,086,000, and total cloud AI spend was EUR 605,000.",
        ),
        CopilotEvalCase(
            case_id="QRY-011",
            category="sql_vendor_ledger",
            question="What is the annual contract value, uptime percentage, critical incidents, and penalty rebate for vendor VND-LOG-03?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_vendor_by_id",
            expected_target_tables=["vendor_contract_sla_ledger"],
            expected_numbers=[540000.0, 98.2, 4.0, 64800.0],
            reference_summary="Vendor VND-LOG-03 (Atlantic Precision Servo Corp) has an annual contract of EUR 540,000, 98.2% uptime, 4 critical incidents, and EUR 64,800 penalty rebate.",
        ),
        CopilotEvalCase(
            case_id="QRY-012",
            category="sql_vendor_ledger",
            question="What is the annual contract value, uptime percentage, critical incidents, and penalty rebate for vendor VND-MED-02?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_vendor_by_id",
            expected_target_tables=["vendor_contract_sla_ledger"],
            expected_numbers=[620000.0, 99.45, 1.0, 31000.0],
            reference_summary="Vendor VND-MED-02 (EuroOptics Cryo Components AG) has an annual contract of EUR 620,000, 99.45% uptime, 1 critical incident, and EUR 31,000 penalty rebate.",
        ),
        CopilotEvalCase(
            case_id="QRY-013",
            category="sql_vendor_ledger",
            question="What is the total annual vendor contract value and total SLA penalty rebates in EUR across all Tier-1 suppliers?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_vendor_summary",
            expected_target_tables=["vendor_contract_sla_ledger"],
            expected_numbers=[2340000.0, 95800.0, 6.0],
            reference_summary="Across all 5 Tier-1 suppliers, total annual contract value is EUR 2,340,000, total penalty rebates are EUR 95,800, and total critical incidents are 6.",
        ),
        CopilotEvalCase(
            case_id="QRY-014",
            category="sql_operational_zone",
            question="What are the mean repair hours and automation coverage percentages for all operational zones ordered by repair hours descending?",
            expected_modality=RouteModality.SQL_ONLY,
            expected_sql_template_id="tpl_zone_ops_all",
            expected_target_tables=["zone_operational_kpis"],
            expected_numbers=[7.8, 71.4, 3.2, 88.5],
            reference_summary="Zone_US_East_Robotics has the highest mean repair hours at 7.8 hours (71.4% automation), while Zone_DACH_Diagnostics has the lowest at 3.2 hours (88.5% automation).",
        ),
        # =====================================================================
        # SLICE B: 10 Unstructured Operational SOP Queries (RAG_ONLY)
        # =====================================================================
        CopilotEvalCase(
            case_id="QRY-015",
            category="rag_policy_sop",
            question="According to policy OPS-SLA-95, what is the minimum quarterly On-Time Delivery percentage and maximum SLA breach count before CAPA escalation?",
            expected_modality=RouteModality.RAG_ONLY,
            expected_passage_ids=["SOP-OPS-101#S1"],
            expected_numbers=[95.0, 5.0],
            reference_summary="Policy OPS-SLA-95 requires at least 95.0% On-Time Delivery and at most 5 SLA breaches per quarter; violations require a CAPA within 5 business days.",
        ),
        CopilotEvalCase(
            case_id="QRY-016",
            category="rag_policy_sop",
            question="Under control OPS-MTTR-6H, what is the maximum Mean Time To Repair ceiling and minimum workflow automation coverage target?",
            expected_modality=RouteModality.RAG_ONLY,
            expected_passage_ids=["SOP-OPS-101#S2"],
            expected_numbers=[6.0, 80.0],
            reference_summary="Control OPS-MTTR-6H sets a maximum Mean Time To Repair ceiling of 6.0 hours and a minimum automation coverage target of 80.0%.",
        ),
        CopilotEvalCase(
            case_id="QRY-017",
            category="rag_policy_sop",
            question="What OPEX variance percentage threshold triggers a CFO Discretionary Spend Freeze under policy FIN-CAP-8PCT?",
            expected_modality=RouteModality.RAG_ONLY,
            expected_passage_ids=["SOP-FIN-202#S1"],
            expected_numbers=[8.0, 3.0],
            reference_summary="Under FIN-CAP-8PCT, an OPEX variance above 8.0% triggers a mandatory CFO Discretionary Spend Freeze and HITL approval, while 3.0% to 8.0% requires a VP Finance memo.",
        ),
        CopilotEvalCase(
            case_id="QRY-018",
            category="rag_policy_sop",
            question="Under directive FIN-GM-58, what is the minimum quarterly gross margin percentage and the quarterly cloud AI spend cap in EUR?",
            expected_modality=RouteModality.RAG_ONLY,
            expected_passage_ids=["SOP-FIN-202#S2"],
            expected_numbers=[58.0, 180000.0],
            reference_summary="Directive FIN-GM-58 mandates a minimum 58.0% gross margin and caps quarterly cloud AI expenditure at EUR 180,000 per zone.",
        ),
        CopilotEvalCase(
            case_id="QRY-019",
            category="rag_policy_sop",
            question="Under clause VND-SLA-995, what supplier uptime thresholds trigger the 5.0% and 12.0% annual contract penalty rebates?",
            expected_modality=RouteModality.RAG_ONLY,
            expected_passage_ids=["SOP-VND-303#S1"],
            expected_numbers=[99.5, 5.0, 12.0, 3.0],
            reference_summary="Clause VND-SLA-995 mandates 99.5% uptime; 99.0%-99.49% triggers a 5.0% rebate, while below 99.0% or 3+ critical incidents triggers a 12.0% penalty rebate.",
        ),
        CopilotEvalCase(
            case_id="QRY-020",
            category="rag_policy_sop",
            question="What are the warning and hard blocking staleness hour limits in standard DQA-FRESH-24H and the maximum null ratio in DQA-NULL-5PCT?",
            expected_modality=RouteModality.RAG_ONLY,
            expected_passage_ids=["SOP-DQA-404#S1", "SOP-DQA-404#S2"],
            expected_numbers=[12.0, 24.0, 48.0, 5.0],
            reference_summary="DQA-FRESH-24H sets a 12.0-hour warning and 24.0-hour blocking ceiling for KPI tables (48.0 hours for backlog partitions), and DQA-NULL-5PCT caps null ratios at 5.0%.",
        ),
        CopilotEvalCase(
            case_id="QRY-021",
            category="rag_policy_sop",
            question="Which SQL keywords are banned by AST policy SQL-AST-RO and what numerical tolerance is enforced by NUM-PARITY-100?",
            expected_modality=RouteModality.RAG_ONLY,
            expected_passage_ids=["SOP-SQL-505#S1", "SOP-SQL-505#S2"],
            expected_numbers=[0.01],
            reference_summary="Policy SQL-AST-RO blocks INSERT, UPDATE, DELETE, DROP, ALTER, ATTACH, and PRAGMA, while NUM-PARITY-100 verifies every number within a 0.01 tolerance.",
        ),
        CopilotEvalCase(
            case_id="QRY-022",
            category="rag_policy_sop",
            question="How does control HITL-DRIFT-SHA compute the composite evidence SHA-256 digest and what happens when a SQL snapshot changes?",
            expected_modality=RouteModality.RAG_ONLY,
            expected_passage_ids=["SOP-HITL-606#S1", "SOP-HITL-606#S2"],
            expected_numbers=[],
            reference_summary="Control HITL-DRIFT-SHA binds approvals to SHA256(normalized_question || sql_snapshot_sha256 || sorted_passage_sha256s || answer_sha256) and transitions drifted records to REJECTED.",
        ),
        CopilotEvalCase(
            case_id="QRY-023",
            category="rag_policy_sop",
            question="According to framework ARCH-BVA-01 and target ARCH-COST-20MS, when should we build a governed hybrid copilot and what is the token reduction target?",
            expected_modality=RouteModality.RAG_ONLY,
            expected_passage_ids=["SOP-AI-707#S1", "SOP-AI-707#S2"],
            expected_numbers=[25.0, 75.0],
            reference_summary="Framework ARCH-BVA-01 mandates building a governed hybrid copilot when strict numerical parity, freshness gates, and HITL audit trails are required, targeting <25 ms CPU latency and 75.0% token reduction.",
        ),
        CopilotEvalCase(
            case_id="QRY-024",
            category="rag_policy_sop",
            question="Under GDPR-WH-90D and GDPR-PURGE-14D, what are the audit log retention period and the Article 17 erasure deadline?",
            expected_modality=RouteModality.RAG_ONLY,
            expected_passage_ids=["SOP-GDPR-808#S1", "SOP-GDPR-808#S2"],
            expected_numbers=[90.0, 14.0],
            reference_summary="GDPR-WH-90D mandates 90-day audit retention in eu-central-1, and GDPR-PURGE-14D requires purging revoked personal identifiers within 14 calendar days.",
        ),
        # =====================================================================
        # SLICE C: 10 Combined Multi-Source Synthesis Queries (HYBRID_MULTI_SOURCE)
        # Bridges live SQL KPIs + Unstructured SOP Governance Rules!
        # =====================================================================
        CopilotEvalCase(
            case_id="QRY-025",
            category="hybrid_ops_compliance",
            question="Which operational zone violated the OPS-SLA-95 minimum 95.0% on-time delivery or 5-breach cap in 2026-Q3, and what action is required?",
            expected_modality=RouteModality.HYBRID_MULTI_SOURCE,
            expected_sql_template_id="tpl_zone_ops_all",
            expected_target_tables=["zone_operational_kpis"],
            expected_passage_ids=["SOP-OPS-101#S1"],
            expected_numbers=[91.2, 9.0, 95.0, 5.0],
            reference_summary="Zone_US_East_Robotics recorded 91.2% on-time delivery and 9 SLA breaches in 2026-Q3, violating the OPS-SLA-95 thresholds of 95.0% OTD and 5 max breaches and requiring a CAPA within 5 business days.",
        ),
        CopilotEvalCase(
            case_id="QRY-026",
            category="hybrid_ops_compliance",
            question="Compare Zone_US_East_Robotics mean repair hours and automation coverage in 2026-Q3 against the OPS-MTTR-6H operational thresholds.",
            expected_modality=RouteModality.HYBRID_MULTI_SOURCE,
            expected_sql_template_id="tpl_zone_ops_by_id",
            expected_target_tables=["zone_operational_kpis"],
            expected_passage_ids=["SOP-OPS-101#S2"],
            expected_numbers=[7.8, 71.4, 6.0, 80.0],
            reference_summary="Zone_US_East_Robotics recorded 7.8 mean repair hours and 71.4% automation coverage, breaching the OPS-MTTR-6H 6.0-hour MTTR ceiling and 80.0% automation target.",
        ),
        CopilotEvalCase(
            case_id="QRY-027",
            category="hybrid_fin_compliance",
            question="Which zone triggered the FIN-CAP-8PCT CFO Discretionary Spend Freeze in 2026-Q3 based on its OPEX variance percentage, and which zone requires a VP Finance memo?",
            expected_modality=RouteModality.HYBRID_MULTI_SOURCE,
            expected_sql_template_id="tpl_zone_fin_all",
            expected_target_tables=["zone_financial_kpis"],
            expected_passage_ids=["SOP-FIN-202#S1"],
            expected_numbers=[14.0, 4.5, 8.0, 3.0],
            reference_summary="Zone_US_East_Robotics recorded a 14.0% OPEX variance (exceeding the 8.0% FIN-CAP-8PCT ceiling, triggering a CFO Spend Freeze), while Zone_EMEA_Imaging recorded 4.5% variance (between 3.0% and 8.0%, requiring a VP Finance memo).",
        ),
        CopilotEvalCase(
            case_id="QRY-028",
            category="hybrid_fin_compliance",
            question="Evaluate Zone_US_East_Robotics 2026-Q3 gross margin percentage and cloud AI spend against directive FIN-GM-58.",
            expected_modality=RouteModality.HYBRID_MULTI_SOURCE,
            expected_sql_template_id="tpl_zone_fin_by_id",
            expected_target_tables=["zone_financial_kpis"],
            expected_passage_ids=["SOP-FIN-202#S2"],
            expected_numbers=[54.8, 210000.0, 58.0, 180000.0],
            reference_summary="Zone_US_East_Robotics recorded 54.8% gross margin and EUR 210,000 cloud AI spend, violating both the FIN-GM-58 minimum 58.0% gross margin and the EUR 180,000 AI spend cap.",
        ),
        CopilotEvalCase(
            case_id="QRY-029",
            category="hybrid_fin_compliance",
            question="Did Zone_DACH_Diagnostics comply with both FIN-CAP-8PCT OPEX variance rules and FIN-GM-58 gross margin and AI spend limits in 2026-Q3?",
            expected_modality=RouteModality.HYBRID_MULTI_SOURCE,
            expected_sql_template_id="tpl_zone_fin_by_id",
            expected_target_tables=["zone_financial_kpis"],
            expected_passage_ids=["SOP-FIN-202#S1", "SOP-FIN-202#S2"],
            expected_numbers=[-2.93, 64.2, 145000.0, 8.0, 58.0, 180000.0],
            reference_summary="Yes: Zone_DACH_Diagnostics achieved -2.93% OPEX variance (below the 8.0% cap), 64.2% gross margin (above the 58.0% floor), and EUR 145,000 cloud AI spend (below the EUR 180,000 cap).",
        ),
        CopilotEvalCase(
            case_id="QRY-030",
            category="hybrid_vendor_compliance",
            question="Why was supplier VND-LOG-03 assessed a EUR 64,800 penalty rebate in 2026-Q3 under clause VND-SLA-995?",
            expected_modality=RouteModality.HYBRID_MULTI_SOURCE,
            expected_sql_template_id="tpl_vendor_by_id",
            expected_target_tables=["vendor_contract_sla_ledger"],
            expected_passage_ids=["SOP-VND-303#S1"],
            expected_numbers=[540000.0, 98.2, 4.0, 64800.0, 12.0],
            reference_summary="Supplier VND-LOG-03 recorded 98.2% uptime (<99.0%) and 4 critical incidents (>=3) on its EUR 540,000 contract, triggering the 12.0% penalty rebate of EUR 64,800 under VND-SLA-995.",
        ),
        CopilotEvalCase(
            case_id="QRY-031",
            category="hybrid_vendor_compliance",
            question="Why was supplier VND-MED-02 assessed a EUR 31,000 penalty rebate in 2026-Q3 under clause VND-SLA-995?",
            expected_modality=RouteModality.HYBRID_MULTI_SOURCE,
            expected_sql_template_id="tpl_vendor_by_id",
            expected_target_tables=["vendor_contract_sla_ledger"],
            expected_passage_ids=["SOP-VND-303#S1"],
            expected_numbers=[620000.0, 99.45, 31000.0, 5.0],
            reference_summary="Supplier VND-MED-02 recorded 99.45% uptime (between 99.0% and 99.49%) on its EUR 620,000 annual contract, triggering the 5.0% penalty rebate of EUR 31,000 under VND-SLA-995.",
        ),
        CopilotEvalCase(
            case_id="QRY-032",
            category="hybrid_vendor_compliance",
            question="Which Tier-1 suppliers exceed the VND-BOARD-500K annual contract threshold of EUR 500,000 and require dual VP Procurement and CISO resilience sign-off?",
            expected_modality=RouteModality.HYBRID_MULTI_SOURCE,
            expected_sql_template_id="tpl_vendor_all",
            expected_target_tables=["vendor_contract_sla_ledger"],
            expected_passage_ids=["SOP-VND-303#S2"],
            expected_numbers=[620000.0, 540000.0, 500000.0],
            reference_summary="VND-MED-02 (EUR 620,000) and VND-LOG-03 (EUR 540,000) exceed the EUR 500,000 threshold under VND-BOARD-500K and require dual VP Procurement and CISO sign-off.",
        ),
        CopilotEvalCase(
            case_id="QRY-033",
            category="hybrid_ops_compliance",
            question="Did Zone_DACH_Diagnostics and Zone_APAC_LabSystems both meet the OPS-MTTR-6H repair time and 80.0% automation coverage targets in 2026-Q3?",
            expected_modality=RouteModality.HYBRID_MULTI_SOURCE,
            expected_sql_template_id="tpl_zone_ops_all",
            expected_target_tables=["zone_operational_kpis"],
            expected_passage_ids=["SOP-OPS-101#S2"],
            expected_numbers=[3.2, 88.5, 3.9, 84.2, 6.0, 80.0],
            reference_summary="Yes: Zone_DACH_Diagnostics (3.2 repair hours, 88.5% automation) and Zone_APAC_LabSystems (3.9 repair hours, 84.2% automation) both met the OPS-MTTR-6H <=6.0h and >=80.0% targets.",
        ),
        CopilotEvalCase(
            case_id="QRY-034",
            category="hybrid_fin_compliance",
            question="How does Zone_EMEA_Imaging 2026-Q3 OPEX variance and cloud AI spend compare against FIN-CAP-8PCT and FIN-GM-58?",
            expected_modality=RouteModality.HYBRID_MULTI_SOURCE,
            expected_sql_template_id="tpl_zone_fin_by_id",
            expected_target_tables=["zone_financial_kpis"],
            expected_passage_ids=["SOP-FIN-202#S1", "SOP-FIN-202#S2"],
            expected_numbers=[4.5, 118000.0, 61.5, 8.0, 180000.0],
            reference_summary="Zone_EMEA_Imaging had a 4.5% OPEX variance (requiring a VP Finance memo under FIN-CAP-8PCT), while its 61.5% gross margin and EUR 118,000 AI spend complied with FIN-GM-58.",
        ),
        # =====================================================================
        # SLICE D: 6 Stale-Partition & Data-Freshness Blocked Queries (BLOCKED_DATA_QUALITY)
        # =====================================================================
        CopilotEvalCase(
            case_id="QRY-035",
            category="freshness_blocked_backlog",
            question="How many backordered SKUs and blocked orders in EUR are in legacy_supply_backlog_partition for Zone_US_East_Robotics?",
            expected_modality=RouteModality.BLOCKED_DATA_QUALITY,
            expected_target_tables=["legacy_supply_backlog_partition"],
            expected_passage_ids=["SOP-DQA-404#S1"],
            expect_freshness_block=True,
            expected_numbers=[222.0, 48.0],
            reference_summary="BLOCKED BY DATA QUALITY GATE: Table legacy_supply_backlog_partition is 222.0 hours old (exceeding max_staleness_hours=48.0 under DQA-FRESH-24H).",
        ),
        CopilotEvalCase(
            case_id="QRY-036",
            category="freshness_blocked_backlog",
            question="What is the total blocked_orders_eur across all zones in the legacy_supply_backlog_partition table?",
            expected_modality=RouteModality.BLOCKED_DATA_QUALITY,
            expected_target_tables=["legacy_supply_backlog_partition"],
            expected_passage_ids=["SOP-DQA-404#S1"],
            expect_freshness_block=True,
            expected_numbers=[222.0, 48.0],
            reference_summary="BLOCKED BY DATA QUALITY GATE: Table legacy_supply_backlog_partition is 222.0 hours old (exceeding max_staleness_hours=48.0 under DQA-FRESH-24H).",
        ),
        CopilotEvalCase(
            case_id="QRY-037",
            category="freshness_blocked_backlog",
            question="Compare backordered_skus for Zone_DACH_Diagnostics and Zone_EMEA_Imaging from legacy_supply_backlog_partition.",
            expected_modality=RouteModality.BLOCKED_DATA_QUALITY,
            expected_target_tables=["legacy_supply_backlog_partition"],
            expected_passage_ids=["SOP-DQA-404#S1"],
            expect_freshness_block=True,
            expected_numbers=[222.0, 48.0],
            reference_summary="BLOCKED BY DATA QUALITY GATE: Table legacy_supply_backlog_partition is 222.0 hours old (exceeding max_staleness_hours=48.0 under DQA-FRESH-24H).",
        ),
        CopilotEvalCase(
            case_id="QRY-038",
            category="freshness_blocked_backlog",
            question="List all partitions in legacy_supply_backlog_partition where blocked_orders_eur exceeds EUR 500,000.",
            expected_modality=RouteModality.BLOCKED_DATA_QUALITY,
            expected_target_tables=["legacy_supply_backlog_partition"],
            expected_passage_ids=["SOP-DQA-404#S1"],
            expect_freshness_block=True,
            expected_numbers=[222.0, 48.0],
            reference_summary="BLOCKED BY DATA QUALITY GATE: Table legacy_supply_backlog_partition is 222.0 hours old (exceeding max_staleness_hours=48.0 under DQA-FRESH-24H).",
        ),
        CopilotEvalCase(
            case_id="QRY-039",
            category="freshness_blocked_future_clock",
            question="As of 2026-10-30, what were the units shipped for Zone_DACH_Diagnostics if zone_operational_kpis has not refreshed since 2026-10-27?",
            as_of_utc="2026-10-30T12:00:00Z",
            expected_modality=RouteModality.BLOCKED_DATA_QUALITY,
            expected_target_tables=["zone_operational_kpis"],
            expected_passage_ids=["SOP-DQA-404#S1"],
            expect_freshness_block=True,
            expected_numbers=[75.0, 24.0],
            reference_summary="BLOCKED BY DATA QUALITY GATE: As of 2026-10-30T12:00:00Z, zone_operational_kpis is 75.0 hours old, exceeding the 24.0-hour DQA-FRESH-24H ceiling.",
        ),
        CopilotEvalCase(
            case_id="QRY-040",
            category="freshness_blocked_future_clock",
            question="As of 2026-10-30, what was the actual OPEX for Zone_US_East_Robotics if zone_financial_kpis has not refreshed since 2026-10-27?",
            as_of_utc="2026-10-30T12:00:00Z",
            expected_modality=RouteModality.BLOCKED_DATA_QUALITY,
            expected_target_tables=["zone_financial_kpis"],
            expected_passage_ids=["SOP-DQA-404#S1"],
            expect_freshness_block=True,
            expected_numbers=[74.5, 24.0],
            reference_summary="BLOCKED BY DATA QUALITY GATE: As of 2026-10-30T12:00:00Z, zone_financial_kpis is 74.5 hours old, exceeding the 24.0-hour DQA-FRESH-24H ceiling.",
        ),
    ]


def materialize_data_assets(root_dir: Path) -> None:
    """Write relational tables, unstructured operational documents, and 40 benchmark cases to data/."""
    wh_dir = root_dir / "data" / "warehouse"
    doc_dir = root_dir / "data" / "documents"
    bench_dir = root_dir / "data" / "benchmark"
    wh_dir.mkdir(parents=True, exist_ok=True)
    doc_dir.mkdir(parents=True, exist_ok=True)
    bench_dir.mkdir(parents=True, exist_ok=True)

    warehouse_snapshot = {
        "contracts": [c.model_dump(mode="json") for c in get_table_contracts()],
        "tables": {
            "zone_operational_kpis": ZONE_OPERATIONAL_ROWS,
            "zone_financial_kpis": ZONE_FINANCIAL_ROWS,
            "vendor_contract_sla_ledger": VENDOR_SLA_ROWS,
            "legacy_supply_backlog_partition": LEGACY_STALE_BACKLOG_ROWS,
        },
    }
    (wh_dir / "warehouse_tables.json").write_text(
        json.dumps(warehouse_snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    passages = get_operational_passages()
    (doc_dir / "operational_sops.json").write_text(
        json.dumps([p.model_dump(mode="json") for p in passages], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    eval_dataset = CopilotEvalDatasetFile(
        dataset_name="enterprise-hybrid-data-copilot-40query-benchmark",
        schema_version="1.0.0",
        default_as_of_utc="2026-10-27T12:00:00Z",
        description=(
            "40 labelled enterprise decision-support queries across 4 slices: "
            "14 sql_only, 10 rag_only, 10 hybrid_multi_source, and 6 blocked_data_quality."
        ),
        cases=get_40_eval_cases(),
    )
    (bench_dir / "copilot_eval_cases.json").write_text(
        json.dumps(eval_dataset.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
