"""Data Freshness & Quality Gate (`src/copilot/data_quality.py`).

Inspects relational KPI tables for refresh timestamp freshness, row-count bounds,
column null ratios, and schema contracts prior to executing any analytics or RAG workflow.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from copilot.datasets import get_table_contracts, sha256_hex
from copilot.schemas import (
    DataReadinessReport,
    ReadinessStatus,
    TableContract,
    TableQualityCheck,
)


def parse_utc_timestamp(ts_str: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp string (e.g. '2026-10-27T12:00:00Z')."""
    cleaned = ts_str.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def inspect_single_table(
    conn: sqlite3.Connection,
    contract: TableContract,
    as_of_utc: str = "2026-10-27T12:00:00Z",
) -> TableQualityCheck:
    """Inspect a single SQLite table against its declarative TableContract."""
    as_of_dt = parse_utc_timestamp(as_of_utc)
    table = contract.table_name

    # 1. Inspect table existence and columns via PRAGMA table_info
    pragma_rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    existing_cols = [str(r[1]) for r in pragma_rows]

    if not existing_cols:
        return TableQualityCheck(
            table_name=table,
            status=ReadinessStatus.BLOCKED_CONTRACT,
            row_count=0,
            latest_refresh_utc=None,
            staleness_hours=9999.0,
            max_null_ratio_observed=1.0,
            null_ratios_by_column={},
            missing_columns=list(contract.required_columns),
            schema_valid=False,
            table_sha256=sha256_hex(f"MISSING:{table}"),
            reasons=[f"Table {table!r} does not exist in relational warehouse."],
        )

    missing_cols = [c for c in contract.required_columns if c not in existing_cols]
    schema_valid = len(missing_cols) == 0

    # 2. Fetch all rows deterministically to compute row_count, null ratios, refresh timestamp, and SHA-256
    col_list_sql = ", ".join(existing_cols)
    raw_rows = conn.execute(f"SELECT {col_list_sql} FROM {table} ORDER BY 1 ASC;").fetchall()
    row_count = len(raw_rows)

    dict_rows = [
        {existing_cols[i]: row[i] for i in range(len(existing_cols))}
        for row in raw_rows
    ]
    canonical_table_json = json.dumps(dict_rows, sort_keys=True, separators=(",", ":"))
    table_sha256 = sha256_hex(f"{table}:{canonical_table_json}")

    reasons: list[str] = []
    if not schema_valid:
        reasons.append(f"Missing required schema columns: {', '.join(missing_cols)}")

    if row_count < contract.min_rows or row_count > contract.max_rows:
        reasons.append(
            f"Row count {row_count} violates contract bounds [{contract.min_rows}, {contract.max_rows}]."
        )

    # 3. Compute column null ratios
    null_ratios: dict[str, float] = {}
    for col in existing_cols:
        if row_count == 0:
            null_ratios[col] = 1.0
        else:
            null_count = sum(1 for r in dict_rows if r.get(col) is None)
            null_ratios[col] = round(null_count / row_count, 6)

    max_null_obs = max(null_ratios.values()) if null_ratios else 0.0
    if max_null_obs > contract.max_null_ratio:
        reasons.append(
            f"Maximum observed column null ratio {max_null_obs:.4f} exceeds contract limit {contract.max_null_ratio:.4f}."
        )

    # 4. Evaluate timestamp freshness
    latest_ts_str: str | None = None
    staleness_hours = 0.0
    if contract.timestamp_column in existing_cols and row_count > 0:
        ts_values = [
            str(r[contract.timestamp_column])
            for r in dict_rows
            if r.get(contract.timestamp_column) is not None
        ]
        if ts_values:
            latest_dt = max(parse_utc_timestamp(ts) for ts in ts_values)
            latest_ts_str = latest_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            staleness_hours = round(
                max(0.0, (as_of_dt - latest_dt).total_seconds() / 3600.0), 2
            )
        else:
            staleness_hours = 9999.0
            reasons.append(f"Timestamp column {contract.timestamp_column!r} contains only NULL values.")
    else:
        staleness_hours = 9999.0
        reasons.append(f"Timestamp column {contract.timestamp_column!r} unavailable for freshness check.")

    # Determine status precedence: BLOCKED_CONTRACT > BLOCKED_STALE > WARN_STALE > READY
    if (
        not schema_valid
        or row_count < contract.min_rows
        or row_count > contract.max_rows
        or max_null_obs > contract.max_null_ratio
    ):
        status = ReadinessStatus.BLOCKED_CONTRACT
    elif staleness_hours > contract.max_staleness_hours:
        status = ReadinessStatus.BLOCKED_STALE
        reasons.append(
            f"Table {table} refresh ({latest_ts_str}) is {staleness_hours:.1f} hours old as of {as_of_utc}, "
            f"exceeding max_staleness_hours={contract.max_staleness_hours:.1f} (DQA-FRESH-24H)."
        )
    elif staleness_hours > contract.warn_staleness_hours:
        status = ReadinessStatus.WARN_STALE
        reasons.append(
            f"Table {table} refresh ({latest_ts_str}) is {staleness_hours:.1f} hours old, "
            f"exceeding warning threshold {contract.warn_staleness_hours:.1f} hours."
        )
    else:
        status = ReadinessStatus.READY
        reasons.append(
            f"Table {table} passed schema, row-count ({row_count}), null-ratio ({max_null_obs:.3f}), "
            f"and freshness ({staleness_hours:.1f}h <= {contract.max_staleness_hours:.1f}h) checks."
        )

    return TableQualityCheck(
        table_name=table,
        status=status,
        row_count=row_count,
        latest_refresh_utc=latest_ts_str,
        staleness_hours=staleness_hours,
        max_null_ratio_observed=max_null_obs,
        null_ratios_by_column=null_ratios,
        missing_columns=missing_cols,
        schema_valid=schema_valid,
        table_sha256=table_sha256,
        reasons=reasons,
    )


def evaluate_warehouse_readiness(
    conn: sqlite3.Connection,
    contracts: list[TableContract] | None = None,
    as_of_utc: str = "2026-10-27T12:00:00Z",
) -> DataReadinessReport:
    """Inspect all relational tables and return a structured DataReadinessReport."""
    active_contracts = contracts or get_table_contracts()
    checks: list[TableQualityCheck] = []
    healthy: list[str] = []
    warnings: list[str] = []
    blocked: list[str] = []

    for contract in active_contracts:
        chk = inspect_single_table(conn, contract, as_of_utc=as_of_utc)
        checks.append(chk)
        if chk.status == ReadinessStatus.READY:
            healthy.append(chk.table_name)
        elif chk.status == ReadinessStatus.WARN_STALE:
            warnings.append(chk.table_name)
        else:
            blocked.append(chk.table_name)

    db_manifest = "|".join(f"{c.table_name}:{c.table_sha256}" for c in checks)
    database_sha256 = sha256_hex(db_manifest)

    # Core operational/financial/vendor tables ready check
    core_tables = {"zone_operational_kpis", "zone_financial_kpis", "vendor_contract_sla_ledger"}
    core_blocked = [t for t in blocked if t in core_tables]

    if core_blocked:
        overall = ReadinessStatus.BLOCKED_STALE
    elif blocked or warnings:
        overall = ReadinessStatus.WARN_STALE
    else:
        overall = ReadinessStatus.READY

    return DataReadinessReport(
        as_of_utc=as_of_utc,
        overall_status=overall,
        can_execute_queries=(len(core_blocked) == 0),
        database_sha256=database_sha256,
        tables=checks,
        healthy_tables=healthy,
        warning_tables=warnings,
        blocked_tables=blocked,
    )


def check_target_tables_readiness(
    report: DataReadinessReport,
    target_tables: list[str],
) -> tuple[bool, str | None]:
    """Verify whether all target_tables required by a query pass the Data Quality Gate."""
    by_name = {t.table_name: t for t in report.tables}
    blocked_reasons: list[str] = []

    for tbl in target_tables:
        chk = by_name.get(tbl)
        if chk is None:
            blocked_reasons.append(f"Table {tbl!r} is not registered in warehouse contracts.")
        elif chk.status in (ReadinessStatus.BLOCKED_STALE, ReadinessStatus.BLOCKED_CONTRACT):
            blocked_reasons.append(" ".join(chk.reasons))

    if blocked_reasons:
        return False, "BLOCKED BY DATA QUALITY GATE: " + " | ".join(blocked_reasons)
    return True, None
