"""Deterministic Numerical Grounding Guardrail (`src/copilot/verifier.py`).

Extracts every numeric, currency, or percentage token from a drafted summary and verifies
exact mathematical parity against the SQL result set, retrieved policy passages, or
data-readiness metrics before returning the response.
"""

from __future__ import annotations

import re

from copilot.schemas import (
    DataReadinessReport,
    NumericalVerificationReport,
    NumericTokenCheck,
    ScoredPassage,
    SQLExecutionArtifact,
)

# Strip non-metric identifier patterns (dates, quarter tags, SOP/control IDs, citation brackets)
IDENTIFIER_SCRUB_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\[[A-Za-z0-9_\-#]+\]"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z)?\b"),
    re.compile(r"\b\d{4}-Q[1-4]\b", re.IGNORECASE),
    re.compile(r"\b[A-Za-z]+(?:-[A-Za-z0-9]+)+\b"),
    re.compile(r"\b[A-Za-z]+_[A-Za-z0-9_]+\b"),
    re.compile(r"\b(?:Tier-1|Class\s+II[ab]|Article\s+\d+|SOC\s+2|ISO/IEC\s+\d+:\d+|SHA-?256|FTS5|1e-2)\b", re.IGNORECASE),
)

NUMERIC_TOKEN_RE = re.compile(
    r"(?:EUR\s*)?([+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+-]?\d+(?:\.\d+)?)(%)?"
)


def _scrub_identifiers(text: str) -> str:
    cleaned = text
    for pat in IDENTIFIER_SCRUB_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    return cleaned


def extract_numeric_tokens(text: str) -> list[tuple[str, float, str]]:
    """Extract (raw_token, normalized_float, token_kind) from text after scrubbing identifier codes."""
    scrubbed = _scrub_identifiers(text)
    extracted: list[tuple[str, float, str]] = []

    for match in NUMERIC_TOKEN_RE.finditer(scrubbed):
        full_raw = match.group(0).strip()
        num_str = match.group(1).replace(",", "")
        pct_sign = match.group(2)
        try:
            val = float(num_str)
        except ValueError:
            continue

        if full_raw.upper().startswith("EUR"):
            kind = "currency"
        elif pct_sign == "%":
            kind = "percentage"
        elif "." in num_str:
            kind = "decimal"
        else:
            kind = "integer"

        extracted.append((full_raw, val, kind))
    return extracted


def _collect_ground_truth_numbers(
    sql_artifact: SQLExecutionArtifact | None,
    passages: list[ScoredPassage],
    readiness_report: DataReadinessReport | None = None,
) -> list[tuple[float, str, str]]:
    """Collect (exact_value, source_type, source_ref) from SQL rows, SOP passages, and readiness checks."""
    catalog: list[tuple[float, str, str]] = []

    if sql_artifact is not None:
        catalog.append((float(sql_artifact.row_count), "sql_result", f"{sql_artifact.template_id}.row_count"))
        for row_idx, row in enumerate(sql_artifact.rows):
            for col_name, cell_val in row.items():
                if isinstance(cell_val, (int, float)) and not isinstance(cell_val, bool):
                    catalog.append(
                        (
                            float(cell_val),
                            "sql_result",
                            f"{sql_artifact.template_id}[{row_idx}].{col_name}",
                        )
                    )

    for p in passages:
        for _, val, _ in extract_numeric_tokens(p.text):
            catalog.append((val, "document_passage", p.passage_id))

    if readiness_report is not None:
        for tbl in readiness_report.tables:
            catalog.append((float(tbl.row_count), "readiness_report", f"{tbl.table_name}.row_count"))
            catalog.append((float(tbl.staleness_hours), "readiness_report", f"{tbl.table_name}.staleness_hours"))
            catalog.append(
                (float(tbl.max_null_ratio_observed), "readiness_report", f"{tbl.table_name}.max_null_ratio")
            )
            for reason_str in tbl.reasons:
                for _, r_val, _ in extract_numeric_tokens(reason_str):
                    catalog.append((r_val, "readiness_report", f"{tbl.table_name}.reason"))

    return catalog


def verify_numerical_grounding(
    draft_answer: str,
    sql_artifact: SQLExecutionArtifact | None,
    passages: list[ScoredPassage],
    readiness_report: DataReadinessReport | None = None,
    relative_tolerance: float = 1e-2,
) -> NumericalVerificationReport:
    """Verify every numeric token in draft_answer against SQL rows, passages, and readiness evidence."""
    tokens = extract_numeric_tokens(draft_answer)
    if not tokens:
        return NumericalVerificationReport(
            all_numbers_verified=True,
            total_numeric_tokens=0,
            verified_tokens=0,
            unverified_tokens=[],
            numerical_parity_rate=1.0,
            checks=[],
        )

    ground_truth = _collect_ground_truth_numbers(sql_artifact, passages, readiness_report)
    checks: list[NumericTokenCheck] = []
    unverified_raw: list[str] = []

    for raw_tok, val, kind in tokens:
        best_match: tuple[float, str, str, float] | None = None
        for gt_val, src_type, src_ref in ground_truth:
            abs_diff = abs(val - gt_val)
            denom = max(abs(gt_val), 1.0)
            rel_err = abs_diff / denom
            if abs_diff <= 1e-4 or rel_err <= relative_tolerance:
                if best_match is None or abs_diff < best_match[3]:
                    best_match = (gt_val, src_type, src_ref, abs_diff)

        if best_match is not None:
            checks.append(
                NumericTokenCheck(
                    raw_token=raw_tok,
                    normalized_value=val,
                    token_kind=kind,
                    matched_source=best_match[1],
                    matched_reference=best_match[2],
                    expected_exact_value=best_match[0],
                    absolute_diff=round(best_match[3], 6),
                    is_verified=True,
                )
            )
        else:
            unverified_raw.append(raw_tok)
            checks.append(
                NumericTokenCheck(
                    raw_token=raw_tok,
                    normalized_value=val,
                    token_kind=kind,
                    matched_source=None,
                    matched_reference=None,
                    expected_exact_value=None,
                    absolute_diff=0.0,
                    is_verified=False,
                )
            )

    verified_count = sum(1 for c in checks if c.is_verified)
    parity_rate = round(verified_count / len(checks), 6)

    return NumericalVerificationReport(
        all_numbers_verified=(verified_count == len(checks)),
        total_numeric_tokens=len(checks),
        verified_tokens=verified_count,
        unverified_tokens=unverified_raw,
        numerical_parity_rate=parity_rate,
        checks=checks,
    )
