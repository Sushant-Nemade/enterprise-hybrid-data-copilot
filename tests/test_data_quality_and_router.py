"""Tests for Data Freshness & Quality Gate, AST SQL Validation, and Hybrid SQL+RAG Routing."""

from __future__ import annotations

import sqlite3

import pytest

from copilot.data_quality import (
    check_target_tables_readiness,
    evaluate_warehouse_readiness,
    inspect_single_table,
)
from copilot.datasets import get_table_contracts, seed_sqlite_warehouse
from copilot.router import HybridDataCopilotRouter, validate_sql_ast_read_only
from copilot.schemas import ReadinessStatus, RouteModality, TableContract


def test_warehouse_readiness_detects_ready_and_stale_partitions() -> None:
    conn = sqlite3.connect(":memory:")
    seed_sqlite_warehouse(conn)

    report = evaluate_warehouse_readiness(conn, as_of_utc="2026-10-27T12:00:00Z")
    assert report.can_execute_queries is True
    assert "zone_operational_kpis" in report.healthy_tables
    assert "zone_financial_kpis" in report.healthy_tables
    assert "vendor_contract_sla_ledger" in report.healthy_tables
    assert "legacy_supply_backlog_partition" in report.blocked_tables

    ok_ops, err_ops = check_target_tables_readiness(report, ["zone_operational_kpis"])
    assert ok_ops is True
    assert err_ops is None

    ok_stale, err_stale = check_target_tables_readiness(
        report, ["legacy_supply_backlog_partition"]
    )
    assert ok_stale is False
    assert err_stale is not None
    assert "BLOCKED BY DATA QUALITY GATE" in err_stale


def test_data_quality_gate_blocks_schema_and_null_ratio_violations() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE custom_kpi (zone_id TEXT, metric REAL, refreshed_at_utc TEXT);")
    conn.execute("INSERT INTO custom_kpi VALUES ('Z1', NULL, '2026-10-27T11:00:00Z');")
    conn.execute("INSERT INTO custom_kpi VALUES ('Z2', 10.0, '2026-10-27T11:00:00Z');")

    contract = TableContract(
        table_name="custom_kpi",
        description="Test contract",
        required_columns=["zone_id", "metric", "refreshed_at_utc"],
        timestamp_column="refreshed_at_utc",
        min_rows=2,
        max_rows=10,
        max_null_ratio=0.05,  # 50% nulls in 'metric' violates 5% ceiling
        warn_staleness_hours=12.0,
        max_staleness_hours=24.0,
    )
    chk = inspect_single_table(conn, contract, as_of_utc="2026-10-27T12:00:00Z")
    assert chk.status == ReadinessStatus.BLOCKED_CONTRACT
    assert chk.max_null_ratio_observed == 0.5

    # Missing required column check
    missing_col_contract = TableContract(
        table_name="custom_kpi",
        description="Missing col contract",
        required_columns=["zone_id", "missing_col", "refreshed_at_utc"],
        timestamp_column="refreshed_at_utc",
        min_rows=1,
        max_rows=10,
        max_null_ratio=1.0,
        warn_staleness_hours=12.0,
        max_staleness_hours=24.0,
    )
    chk_missing = inspect_single_table(conn, missing_col_contract, as_of_utc="2026-10-27T12:00:00Z")
    assert chk_missing.status == ReadinessStatus.BLOCKED_CONTRACT
    assert chk_missing.schema_valid is False
    assert "missing_col" in chk_missing.missing_columns
    assert len(get_table_contracts()) == 4


@pytest.mark.parametrize(
    "malicious_sql",
    [
        "DROP TABLE zone_operational_kpis",
        "DELETE FROM zone_financial_kpis WHERE 1=1",
        "UPDATE zone_financial_kpis SET revenue_eur = 0",
        "SELECT * FROM zone_operational_kpis; DROP TABLE zone_financial_kpis",
        "SELECT * FROM zone_operational_kpis -- comment injection",
        "PRAGMA table_info(zone_operational_kpis)",
        "SELECT * FROM sqlite_master",
    ],
)
def test_ast_sql_validator_blocks_mutating_and_unsafe_queries(malicious_sql: str) -> None:
    ok, reason, tables = validate_sql_ast_read_only(malicious_sql)
    assert ok is False
    assert tables == []
    assert len(reason) > 5


def test_router_modalities_across_sql_rag_hybrid_and_blocked() -> None:
    router = HybridDataCopilotRouter()

    # 1. SQL_ONLY
    r_sql = router.route_and_execute(
        "What were the units shipped, SLA breach count, and on-time delivery percentage for Zone_DACH_Diagnostics in 2026-Q3?"
    )
    assert r_sql.modality == RouteModality.SQL_ONLY
    assert r_sql.sql_artifact is not None
    assert r_sql.sql_artifact.template_id == "tpl_zone_ops_by_id"
    assert r_sql.retrieved_passages == []

    # 2. RAG_ONLY
    r_rag = router.route_and_execute(
        "According to policy OPS-SLA-95, what is the minimum quarterly On-Time Delivery percentage and maximum SLA breach count?"
    )
    assert r_rag.modality == RouteModality.RAG_ONLY
    assert r_rag.sql_artifact is None
    assert r_rag.retrieved_passages[0].passage_id == "SOP-OPS-101#S1"

    # 3. HYBRID_MULTI_SOURCE
    r_hyb = router.route_and_execute(
        "Which zone triggered the FIN-CAP-8PCT CFO Discretionary Spend Freeze in 2026-Q3 based on its OPEX variance percentage?"
    )
    assert r_hyb.modality == RouteModality.HYBRID_MULTI_SOURCE
    assert r_hyb.sql_artifact is not None
    assert len(r_hyb.retrieved_passages) >= 1
    assert r_hyb.retrieved_passages[0].passage_id == "SOP-FIN-202#S1"

    # 4. BLOCKED_DATA_QUALITY
    r_blk = router.route_and_execute(
        "How many backordered SKUs are in legacy_supply_backlog_partition for Zone_US_East_Robotics?"
    )
    assert r_blk.modality == RouteModality.BLOCKED_DATA_QUALITY
    assert r_blk.blocked_by_freshness_gate is True
    assert r_blk.sql_artifact is None
