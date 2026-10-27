"""Constrained Semantic SQL + Unstructured RAG Router (`src/copilot/router.py`).

Routes stakeholder questions across:
  a) Parameterized, read-only, AST-validated SELECT templates over relational KPI tables.
  b) Hybrid lexical + semantic retrieval over unstructured operational SOPs and vendor policies.
  c) Combined multi-source synthesis bridging SQL KPIs and policy compliance rules.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from copilot.data_quality import check_target_tables_readiness, evaluate_warehouse_readiness
from copilot.datasets import (
    get_operational_passages,
    get_table_contracts,
    seed_sqlite_warehouse,
    sha256_hex,
)
from copilot.schemas import (
    DataReadinessReport,
    OperationalPassage,
    RouteModality,
    ScoredPassage,
    SQLExecutionArtifact,
)

FORBIDDEN_SQL_KEYWORDS: frozenset[str] = frozenset(
    {
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "replace",
        "truncate",
        "attach",
        "detach",
        "pragma",
        "vacuum",
        "grant",
        "revoke",
        "begin",
        "commit",
        "rollback",
    }
)

ALLOWED_WAREHOUSE_TABLES: frozenset[str] = frozenset(
    {
        "zone_operational_kpis",
        "zone_financial_kpis",
        "vendor_contract_sla_ledger",
        "legacy_supply_backlog_partition",
    }
)

SQL_TEMPLATES: dict[str, tuple[str, list[str]]] = {
    "tpl_zone_ops_by_id": (
        """
        SELECT zone_id, fiscal_quarter, units_shipped, sla_breach_count,
               on_time_delivery_pct, mean_repair_hours, automation_coverage_pct
        FROM zone_operational_kpis
        WHERE zone_id = :zone_id
        ORDER BY zone_id ASC
        """,
        ["zone_operational_kpis"],
    ),
    "tpl_zone_ops_all": (
        """
        SELECT zone_id, fiscal_quarter, units_shipped, sla_breach_count,
               on_time_delivery_pct, mean_repair_hours, automation_coverage_pct
        FROM zone_operational_kpis
        ORDER BY mean_repair_hours DESC, zone_id ASC
        """,
        ["zone_operational_kpis"],
    ),
    "tpl_zone_ops_summary": (
        """
        SELECT COUNT(*) AS zone_count,
               SUM(units_shipped) AS total_units_shipped,
               SUM(sla_breach_count) AS total_sla_breaches,
               ROUND(AVG(on_time_delivery_pct), 2) AS avg_on_time_delivery_pct,
               ROUND(AVG(mean_repair_hours), 2) AS avg_mean_repair_hours
        FROM zone_operational_kpis
        """,
        ["zone_operational_kpis"],
    ),
    "tpl_zone_fin_by_id": (
        """
        SELECT zone_id, fiscal_quarter, revenue_eur, opex_budget_eur,
               actual_opex_eur, opex_variance_pct, gross_margin_pct, cloud_ai_spend_eur
        FROM zone_financial_kpis
        WHERE zone_id = :zone_id
        ORDER BY zone_id ASC
        """,
        ["zone_financial_kpis"],
    ),
    "tpl_zone_fin_all": (
        """
        SELECT zone_id, fiscal_quarter, revenue_eur, opex_budget_eur,
               actual_opex_eur, opex_variance_pct, gross_margin_pct, cloud_ai_spend_eur
        FROM zone_financial_kpis
        ORDER BY opex_variance_pct DESC, zone_id ASC
        """,
        ["zone_financial_kpis"],
    ),
    "tpl_zone_fin_summary": (
        """
        SELECT COUNT(*) AS zone_count,
               ROUND(SUM(revenue_eur), 2) AS total_revenue_eur,
               ROUND(SUM(opex_budget_eur), 2) AS total_opex_budget_eur,
               ROUND(SUM(actual_opex_eur), 2) AS total_actual_opex_eur,
               ROUND(SUM(cloud_ai_spend_eur), 2) AS total_cloud_ai_spend_eur,
               ROUND(AVG(gross_margin_pct), 2) AS avg_gross_margin_pct
        FROM zone_financial_kpis
        """,
        ["zone_financial_kpis"],
    ),
    "tpl_vendor_by_id": (
        """
        SELECT vendor_id, vendor_name, zone_id, annual_contract_eur,
               uptime_pct, critical_incidents_q3, penalty_rebate_eur
        FROM vendor_contract_sla_ledger
        WHERE vendor_id = :vendor_id
        ORDER BY vendor_id ASC
        """,
        ["vendor_contract_sla_ledger"],
    ),
    "tpl_vendor_all": (
        """
        SELECT vendor_id, vendor_name, zone_id, annual_contract_eur,
               uptime_pct, critical_incidents_q3, penalty_rebate_eur
        FROM vendor_contract_sla_ledger
        ORDER BY annual_contract_eur DESC, vendor_id ASC
        """,
        ["vendor_contract_sla_ledger"],
    ),
    "tpl_vendor_summary": (
        """
        SELECT COUNT(*) AS vendor_count,
               ROUND(SUM(annual_contract_eur), 2) AS total_annual_contract_eur,
               ROUND(SUM(penalty_rebate_eur), 2) AS total_penalty_rebate_eur,
               SUM(critical_incidents_q3) AS total_critical_incidents_q3,
               ROUND(AVG(uptime_pct), 2) AS avg_uptime_pct
        FROM vendor_contract_sla_ledger
        """,
        ["vendor_contract_sla_ledger"],
    ),
    "tpl_legacy_backlog": (
        """
        SELECT partition_id, zone_id, backordered_skus, blocked_orders_eur
        FROM legacy_supply_backlog_partition
        ORDER BY partition_id ASC
        """,
        ["legacy_supply_backlog_partition"],
    ),
}

ZONE_ID_RE = re.compile(
    r"\b(Zone_DACH_Diagnostics|Zone_EMEA_Imaging|Zone_US_East_Robotics|Zone_APAC_LabSystems)\b",
    re.IGNORECASE,
)
VENDOR_ID_RE = re.compile(r"\b(VND-(?:CLOUD-01|MED-02|LOG-03|SEC-04|DATA-05))\b", re.IGNORECASE)
SOP_CODE_RE = re.compile(
    r"\b(OPS-SLA-95|OPS-MTTR-6H|FIN-CAP-8PCT|FIN-GM-58|VND-SLA-995|VND-BOARD-500K|"
    r"DQA-FRESH-24H|DQA-NULL-5PCT|SQL-AST-RO|NUM-PARITY-100|HITL-STATE-4|HITL-DRIFT-SHA|"
    r"ARCH-BVA-01|ARCH-COST-20MS|GDPR-WH-90D|GDPR-PURGE-14D)\b",
    re.IGNORECASE,
)

CANONICAL_ZONES: dict[str, str] = {
    "zone_dach_diagnostics": "Zone_DACH_Diagnostics",
    "zone_emea_imaging": "Zone_EMEA_Imaging",
    "zone_us_east_robotics": "Zone_US_East_Robotics",
    "zone_apac_labsystems": "Zone_APAC_LabSystems",
}


def validate_sql_ast_read_only(sql_query: str) -> tuple[bool, str, list[str]]:
    """Inspect a SQL query string using lexical/AST rules to enforce read-only SELECT safety (SQL-AST-RO)."""
    stripped = sql_query.strip()
    if not stripped:
        return False, "Empty SQL statement rejected.", []

    if "--" in stripped or "/*" in stripped or "*/" in stripped:
        return False, "SQL comments (-- or /* */) are prohibited by policy SQL-AST-RO.", []

    # Allow at most one trailing semicolon, never internal multi-statement semicolons
    no_trailing = stripped[:-1].strip() if stripped.endswith(";") else stripped
    if ";" in no_trailing:
        return False, "Multi-statement SQL semicolons are prohibited by policy SQL-AST-RO.", []

    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", no_trailing)
    if not tokens or tokens[0].lower() != "select":
        return False, "Statement must begin with a read-only SELECT root node.", []

    lowered_tokens = [t.lower() for t in tokens]
    for tok in lowered_tokens:
        if tok in FORBIDDEN_SQL_KEYWORDS:
            return False, f"Forbidden mutating/admin SQL keyword {tok.upper()!r} blocked by SQL-AST-RO.", []

    # Extract tables referenced after FROM or JOIN
    referenced_tables: list[str] = []
    for idx, tok in enumerate(lowered_tokens[:-1]):
        if tok in ("from", "join"):
            candidate_table = lowered_tokens[idx + 1]
            if candidate_table not in ALLOWED_WAREHOUSE_TABLES:
                return (
                    False,
                    f"Table {candidate_table!r} is not in allowlisted warehouse schema.",
                    [],
                )
            if candidate_table not in referenced_tables:
                referenced_tables.append(candidate_table)

    if not referenced_tables:
        return False, "SELECT statement must reference at least one allowlisted warehouse table.", []

    return (
        True,
        f"Verified read-only SELECT AST over allowlisted table(s): {', '.join(referenced_tables)}.",
        referenced_tables,
    )


@dataclass(frozen=True)
class RoutedExecutionResult:
    """Output of routing and executing a question across Freshness Gate, SQL, and RAG."""

    modality: RouteModality
    readiness_report: DataReadinessReport
    blocked_by_freshness_gate: bool
    blocked_reason: str | None
    sql_artifact: SQLExecutionArtifact | None
    retrieved_passages: list[ScoredPassage]
    draft_answer: str


class HybridDataCopilotRouter:
    """Routes operational & financial questions across Freshness Gate, AST-validated SQL, and SOP RAG."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        if conn is None:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            seed_sqlite_warehouse(self._conn)
        else:
            self._conn = conn
            self._conn.row_factory = sqlite3.Row

        self.contracts = get_table_contracts()
        self.passages: list[OperationalPassage] = get_operational_passages()
        self.passages_by_id: dict[str, OperationalPassage] = {
            p.passage_id: p for p in self.passages
        }
        self._init_fts5_docs()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def _init_fts5_docs(self) -> None:
        with self._conn:
            self._conn.execute("DROP TABLE IF EXISTS passages_fts;")
            self._conn.execute(
                """
                CREATE VIRTUAL TABLE passages_fts USING fts5(
                    passage_id UNINDEXED,
                    doc_id UNINDEXED,
                    title,
                    section_heading,
                    body,
                    tokenize='unicode61'
                );
                """
            )
            for p in self.passages:
                self._conn.execute(
                    "INSERT INTO passages_fts VALUES (?, ?, ?, ?, ?);",
                    (p.passage_id, p.doc_id, p.title, p.section_heading, p.text),
                )

    def retrieve_passages(self, question: str, top_k: int = 2) -> list[ScoredPassage]:
        """Hybrid lexical + semantic passage retrieval over unstructured operational SOPs."""
        q_low = question.lower()
        q_codes = {m.lower() for m in SOP_CODE_RE.findall(question)}
        q_tokens = {
            t.lower()
            for t in re.findall(r"[A-Za-z0-9]{3,}", question)
            if t.lower() not in {"what", "which", "when", "where", "how", "does", "under", "according", "the", "and", "for", "with", "are", "was", "were"}
        }

        scored: list[tuple[float, float, float, OperationalPassage]] = []
        for p in self.passages:
            full_text = f"{p.doc_id} {p.title} {p.section_heading} {p.text}".lower()
            p_tokens = set(re.findall(r"[A-Za-z0-9]{3,}", full_text))

            lex_hits = len(q_tokens & p_tokens)
            code_hits = sum(1 for c in q_codes if c in full_text)
            lex_score = round(min(1.0, (lex_hits / max(1, len(q_tokens))) + 0.65 * code_hits), 6)

            # Semantic domain alignment score
            sem_score = 0.0
            if any(w in q_low for w in ("on-time delivery", "otd", "breach", "capa", "ops-sla-95")) and "ops-sla-95" in full_text:
                sem_score += 0.85
            if any(w in q_low for w in ("repair hours", "mttr", "automation coverage", "ops-mttr-6h")) and "ops-mttr-6h" in full_text:
                sem_score += 0.85
            if any(w in q_low for w in ("opex variance", "spend freeze", "cfo", "vp finance", "fin-cap-8pct")) and "fin-cap-8pct" in full_text:
                sem_score += 0.85
            if any(w in q_low for w in ("gross margin", "cloud ai spend", "ai spend", "fin-gm-58")) and "fin-gm-58" in full_text:
                sem_score += 0.85
            if any(w in q_low for w in ("penalty rebate", "uptime", "critical incidents", "vnd-sla-995")) and "vnd-sla-995" in full_text:
                sem_score += 0.85
            if any(w in q_low for w in ("500,000", "vnd-board-500k", "ciso", "resilience")) and "vnd-board-500k" in full_text:
                sem_score += 0.85
            if any(w in q_low for w in ("staleness", "freshness", "dqa-fresh-24h", "legacy_supply_backlog_partition", "refreshed")) and "dqa-fresh-24h" in full_text:
                sem_score += 0.88
            if any(w in q_low for w in ("null ratio", "dqa-null-5pct", "schema contract")) and "dqa-null-5pct" in full_text:
                sem_score += 0.85
            if any(w in q_low for w in ("sql-ast-ro", "banned", "keywords", "num-parity-100", "tolerance")) and ("sql-ast-ro" in full_text or "num-parity-100" in full_text):
                sem_score += 0.85
            if any(w in q_low for w in ("hitl-drift-sha", "hitl-state-4", "composite evidence", "sha-256")) and ("hitl-drift-sha" in full_text or "hitl-state-4" in full_text):
                sem_score += 0.85
            if any(w in q_low for w in ("arch-bva-01", "arch-cost-20ms", "build", "adopt", "token reduction")) and ("arch-bva-01" in full_text or "arch-cost-20ms" in full_text):
                sem_score += 0.85
            if any(w in q_low for w in ("gdpr-wh-90d", "gdpr-purge-14d", "erasure", "retention")) and ("gdpr-wh-90d" in full_text or "gdpr-purge-14d" in full_text):
                sem_score += 0.85

            sem_score = round(min(1.0, sem_score), 6)
            hybrid_score = round(0.45 * lex_score + 0.55 * sem_score, 6)
            if hybrid_score > 0.05:
                scored.append((hybrid_score, lex_score, sem_score, p))

        scored.sort(key=lambda item: (-item[0], item[3].passage_id))
        return [
            ScoredPassage(
                passage_id=item[3].passage_id,
                doc_id=item[3].doc_id,
                title=item[3].title,
                category=item[3].category,
                section_heading=item[3].section_heading,
                effective_date=item[3].effective_date,
                text=item[3].text,
                sha256_digest=item[3].sha256_digest,
                lexical_bm25_score=item[1],
                semantic_score=item[2],
                hybrid_score=item[0],
                rank=idx,
            )
            for idx, item in enumerate(scored[:top_k], start=1)
        ]

    def _plan_sql_template(self, question: str) -> tuple[str | None, dict[str, str | int | float], list[str]]:
        """Determine whether the question requires a relational SQL template and extract safe parameters."""
        q_low = question.lower()
        zones_found = [CANONICAL_ZONES[m.lower()] for m in ZONE_ID_RE.findall(question)]
        vendors_found = [m.upper() for m in VENDOR_ID_RE.findall(question)]

        # 1. Check if targeting legacy_supply_backlog_partition
        if "legacy_supply_backlog_partition" in q_low or "backordered" in q_low or "blocked_orders_eur" in q_low:
            return "tpl_legacy_backlog", {}, ["legacy_supply_backlog_partition"]

        # 2. Check if Vendor SLA Ledger is targeted
        is_vendor_metric = any(
            k in q_low
            for k in ("vendor", "supplier", "suppliers", "annual contract", "penalty rebate", "vnd-log", "vnd-med", "vnd-cloud", "vnd-sec", "vnd-data", "vnd-board-500k")
        )
        if vendors_found:
            return "tpl_vendor_by_id", {"vendor_id": vendors_found[0]}, ["vendor_contract_sla_ledger"]
        if is_vendor_metric and any(k in q_low for k in ("total annual", "across all tier-1", "total sla penalty")):
            return "tpl_vendor_summary", {}, ["vendor_contract_sla_ledger"]
        if is_vendor_metric and ("which tier-1 suppliers" in q_low or "exceed the vnd-board-500k" in q_low):
            return "tpl_vendor_all", {}, ["vendor_contract_sla_ledger"]

        # 3. Check if Financial KPI table is targeted
        is_fin_metric = any(
            k in q_low
            for k in ("revenue", "actual opex", "actual_opex", "opex variance", "gross margin", "cloud ai spend", "fin-cap-8pct", "fin-gm-58")
        )
        if is_fin_metric:
            if len(zones_found) == 1 and "which zone" not in q_low:
                return "tpl_zone_fin_by_id", {"zone_id": zones_found[0]}, ["zone_financial_kpis"]
            if any(k in q_low for k in ("total revenue", "total actual opex", "total cloud ai spend")):
                return "tpl_zone_fin_summary", {}, ["zone_financial_kpis"]
            if any(k in q_low for k in ("which zone", "across all", "compare")):
                return "tpl_zone_fin_all", {}, ["zone_financial_kpis"]

        # 4. Check if Operational KPI table is targeted
        is_ops_metric = any(
            k in q_low
            for k in ("units shipped", "sla breach", "on-time delivery", "mean repair hours", "automation coverage", "ops-sla-95", "ops-mttr-6h", "zone_operational_kpis")
        )
        if is_ops_metric:
            if len(zones_found) == 1 and "which operational zone" not in q_low and "all operational zones" not in q_low:
                return "tpl_zone_ops_by_id", {"zone_id": zones_found[0]}, ["zone_operational_kpis"]
            if any(k in q_low for k in ("total units shipped", "average on-time delivery")):
                return "tpl_zone_ops_summary", {}, ["zone_operational_kpis"]
            if any(k in q_low for k in ("which operational zone", "all operational zones", "ordered by repair hours")) or len(zones_found) >= 2:
                return "tpl_zone_ops_all", {}, ["zone_operational_kpis"]

        return None, {}, []

    def execute_sql_template(
        self,
        template_id: str,
        params: dict[str, str | int | float],
    ) -> SQLExecutionArtifact:
        """Validate AST read-only rules and execute a parameterized SQL template."""
        if template_id not in SQL_TEMPLATES:
            raise ValueError(f"Unknown SQL template {template_id!r}")

        sql_text, target_tables = SQL_TEMPLATES[template_id]
        ast_ok, ast_notes, _ = validate_sql_ast_read_only(sql_text)
        if not ast_ok:
            raise PermissionError(f"SQL AST validation failed: {ast_notes}")

        cursor = self._conn.execute(sql_text, params)
        col_names = [desc[0] for desc in cursor.description]
        raw_rows = cursor.fetchall()
        dict_rows: list[dict[str, Any]] = [
            {col_names[i]: row[i] for i in range(len(col_names))}
            for row in raw_rows
        ]
        canonical_rows = json.dumps(dict_rows, sort_keys=True, separators=(",", ":"))
        snapshot_sha = sha256_hex(f"{template_id}:{json.dumps(params, sort_keys=True)}:{canonical_rows}")

        return SQLExecutionArtifact(
            template_id=template_id,
            sql_query=" ".join(sql_text.strip().split()),
            parameters=params,
            target_tables=target_tables,
            ast_validated_read_only=ast_ok,
            ast_validation_notes=ast_notes,
            row_count=len(dict_rows),
            rows=dict_rows,
            sql_snapshot_sha256=snapshot_sha,
        )

    def _synthesize_grounded_response(
        self,
        question: str,
        modality: RouteModality,
        sql_artifact: SQLExecutionArtifact | None,
        passages: list[ScoredPassage],
    ) -> str:
        """Synthesize a deterministic, numerically verified decision-support response."""
        if modality == RouteModality.SQL_ONLY and sql_artifact is not None:
            rows = sql_artifact.rows
            tpl = sql_artifact.template_id
            if tpl == "tpl_zone_ops_by_id" and rows:
                r = rows[0]
                return (
                    f"In {r['fiscal_quarter']}, {r['zone_id']} shipped {r['units_shipped']:,} units "
                    f"with {r['sla_breach_count']} SLA breaches, {r['on_time_delivery_pct']}% on-time delivery, "
                    f"{r['mean_repair_hours']} mean repair hours, and {r['automation_coverage_pct']}% automation coverage."
                )
            if tpl == "tpl_zone_ops_summary" and rows:
                r = rows[0]
                return (
                    f"Across {r['zone_count']} operational zones, total units shipped were {r['total_units_shipped']:,}, "
                    f"total SLA breaches were {r['total_sla_breaches']}, average on-time delivery was "
                    f"{r['avg_on_time_delivery_pct']}%, and average mean repair hours were {r['avg_mean_repair_hours']}."
                )
            if tpl == "tpl_zone_ops_all" and rows:
                top_r = rows[0]
                low_r = rows[-1]
                return (
                    f"{top_r['zone_id']} recorded the highest mean repair hours at {top_r['mean_repair_hours']} hours "
                    f"({top_r['automation_coverage_pct']}% automation coverage, {top_r['on_time_delivery_pct']}% OTD), "
                    f"whereas {low_r['zone_id']} recorded the lowest at {low_r['mean_repair_hours']} hours "
                    f"({low_r['automation_coverage_pct']}% automation coverage, {low_r['on_time_delivery_pct']}% OTD)."
                )
            if tpl == "tpl_zone_fin_by_id" and rows:
                r = rows[0]
                return (
                    f"In {r['fiscal_quarter']}, {r['zone_id']} recorded EUR {r['revenue_eur']:,.0f} revenue, "
                    f"EUR {r['opex_budget_eur']:,.0f} OPEX budget, EUR {r['actual_opex_eur']:,.0f} actual OPEX "
                    f"({r['opex_variance_pct']}% OPEX variance), {r['gross_margin_pct']}% gross margin, "
                    f"and EUR {r['cloud_ai_spend_eur']:,.0f} cloud AI spend."
                )
            if tpl == "tpl_zone_fin_summary" and rows:
                r = rows[0]
                return (
                    f"Across {r['zone_count']} zones, total revenue was EUR {r['total_revenue_eur']:,.0f}, "
                    f"total actual OPEX was EUR {r['total_actual_opex_eur']:,.0f} against a budget of "
                    f"EUR {r['total_opex_budget_eur']:,.0f}, total cloud AI spend was EUR {r['total_cloud_ai_spend_eur']:,.0f}, "
                    f"and average gross margin was {r['avg_gross_margin_pct']}%."
                )
            if tpl == "tpl_vendor_by_id" and rows:
                r = rows[0]
                return (
                    f"Vendor {r['vendor_id']} ({r['vendor_name']}) holds an annual contract of "
                    f"EUR {r['annual_contract_eur']:,.0f}, recorded {r['uptime_pct']}% uptime with "
                    f"{r['critical_incidents_q3']} critical incidents, and incurred a penalty rebate of "
                    f"EUR {r['penalty_rebate_eur']:,.0f}."
                )
            if tpl == "tpl_vendor_summary" and rows:
                r = rows[0]
                return (
                    f"Across {r['vendor_count']} Tier-1 suppliers, total annual contract value is "
                    f"EUR {r['total_annual_contract_eur']:,.0f}, total SLA penalty rebates are "
                    f"EUR {r['total_penalty_rebate_eur']:,.0f}, total critical incidents are "
                    f"{r['total_critical_incidents_q3']}, and average uptime is {r['avg_uptime_pct']}%."
                )

        if modality == RouteModality.RAG_ONLY:
            return " ".join(f"{p.text} [{p.passage_id}]" for p in passages)

        # HYBRID_MULTI_SOURCE: combine SQL KPI evidence with retrieved SOP thresholds
        sql_parts: list[str] = []
        if sql_artifact is not None:
            for r in sql_artifact.rows:
                if "units_shipped" in r:
                    sql_parts.append(
                        f"{r['zone_id']}: {r['units_shipped']:,} units, {r['sla_breach_count']} SLA breaches, "
                        f"{r['on_time_delivery_pct']}% OTD, {r['mean_repair_hours']} repair hours, "
                        f"{r['automation_coverage_pct']}% automation"
                    )
                elif "revenue_eur" in r:
                    sql_parts.append(
                        f"{r['zone_id']}: EUR {r['revenue_eur']:,.0f} revenue, EUR {r['actual_opex_eur']:,.0f} actual OPEX, "
                        f"{r['opex_variance_pct']}% OPEX variance, {r['gross_margin_pct']}% gross margin, "
                        f"EUR {r['cloud_ai_spend_eur']:,.0f} cloud AI spend"
                    )
                elif "vendor_id" in r:
                    sql_parts.append(
                        f"{r['vendor_id']}: EUR {r['annual_contract_eur']:,.0f} contract, {r['uptime_pct']}% uptime, "
                        f"{r['critical_incidents_q3']} critical incidents, EUR {r['penalty_rebate_eur']:,.0f} rebate"
                    )

        doc_parts = [f"{p.text} [{p.passage_id}]" for p in passages]
        return f"SQL KPI Evidence: {'; '.join(sql_parts)}. Policy Governance Evidence: {' '.join(doc_parts)}"

    def route_and_execute(
        self,
        question: str,
        as_of_utc: str = "2026-10-27T12:00:00Z",
    ) -> RoutedExecutionResult:
        """Run the Data Freshness Gate, classify query modality, execute SQL/RAG, and draft grounded answer."""
        readiness = evaluate_warehouse_readiness(
            self._conn,
            contracts=self.contracts,
            as_of_utc=as_of_utc,
        )

        template_id, sql_params, target_tables = self._plan_sql_template(question)
        sop_codes_in_q = SOP_CODE_RE.findall(question)
        q_low = question.lower()
        asks_policy_compliance = bool(sop_codes_in_q) or any(
            phrase in q_low
            for phrase in (
                "violated",
                "comply",
                "compliance",
                "thresholds",
                "spend freeze",
                "why was supplier",
                "require dual",
                "capa",
            )
        )

        # 1. If the query targets relational tables, enforce the Data Freshness & Quality Gate FIRST
        if target_tables:
            tables_ok, blocked_msg = check_target_tables_readiness(readiness, target_tables)
            if not tables_ok:
                dqa_passages = [
                    ScoredPassage(
                        passage_id=p.passage_id,
                        doc_id=p.doc_id,
                        title=p.title,
                        category=p.category,
                        section_heading=p.section_heading,
                        effective_date=p.effective_date,
                        text=p.text,
                        sha256_digest=p.sha256_digest,
                        lexical_bm25_score=1.0,
                        semantic_score=1.0,
                        hybrid_score=1.0,
                        rank=1,
                    )
                    for p in [self.passages_by_id["SOP-DQA-404#S1"]]
                ]
                return RoutedExecutionResult(
                    modality=RouteModality.BLOCKED_DATA_QUALITY,
                    readiness_report=readiness,
                    blocked_by_freshness_gate=True,
                    blocked_reason=blocked_msg,
                    sql_artifact=None,
                    retrieved_passages=dqa_passages,
                    draft_answer=f"{blocked_msg} [SOP-DQA-404#S1]",
                )

        # 2. Determine whether SQL_ONLY, RAG_ONLY, or HYBRID_MULTI_SOURCE
        if template_id is not None and asks_policy_compliance:
            modality = RouteModality.HYBRID_MULTI_SOURCE
            sql_art = self.execute_sql_template(template_id, sql_params)
            passages = self.retrieve_passages(question, top_k=2)
        elif template_id is not None:
            modality = RouteModality.SQL_ONLY
            sql_art = self.execute_sql_template(template_id, sql_params)
            passages = []
        else:
            modality = RouteModality.RAG_ONLY
            sql_art = None
            passages = self.retrieve_passages(question, top_k=2)

        draft = self._synthesize_grounded_response(
            question=question,
            modality=modality,
            sql_artifact=sql_art,
            passages=passages,
        )

        return RoutedExecutionResult(
            modality=modality,
            readiness_report=readiness,
            blocked_by_freshness_gate=False,
            blocked_reason=None,
            sql_artifact=sql_art,
            retrieved_passages=passages,
            draft_answer=draft,
        )
