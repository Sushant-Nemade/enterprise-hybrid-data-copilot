"""Strict Pydantic v2 data contracts for Enterprise Hybrid Data Copilot."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

UNSAFE_INPUT_PATTERN = re.compile(
    r"(?:<\s*script|javascript:|onerror\s*=|onload\s*=|[\x00-\x08\x0b\x0c\x0e-\x1f])",
    re.IGNORECASE,
)


def _reject_unsafe_text(value: str, field_name: str) -> str:
    if UNSAFE_INPUT_PATTERN.search(value):
        raise ValueError(f"{field_name} contains disallowed script/HTML injection or ASCII control characters")
    return value


class ReadinessStatus(StrEnum):
    """Data readiness and partition freshness states."""

    READY = "ready"
    WARN_STALE = "warn_stale"
    BLOCKED_STALE = "blocked_stale"
    BLOCKED_CONTRACT = "blocked_contract"


class RouteModality(StrEnum):
    """Query routing modalities across structured SQL and unstructured RAG."""

    SQL_ONLY = "sql_only"
    RAG_ONLY = "rag_only"
    HYBRID_MULTI_SOURCE = "hybrid_multi_source"
    BLOCKED_DATA_QUALITY = "blocked_data_quality"


class WorkflowState(StrEnum):
    """Approval state machine states for Human-in-the-Loop (HITL) governance."""

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class EvaluationArchitectureMode(StrEnum):
    """Build-vs-Adopt architecture modes compared in the 40-query benchmark."""

    UNGOVERNED_PROMPT_SQL = "ungoverned_prompt_sql"
    ADOPT_DOC_ONLY_RAG = "adopt_doc_only_rag"
    BUILD_GOVERNED_HYBRID_COPILOT = "build_governed_hybrid_copilot"


ARCHITECTURE_LABELS: dict[EvaluationArchitectureMode, str] = {
    EvaluationArchitectureMode.UNGOVERNED_PROMPT_SQL: "Ungoverned Prompt-to-SQL Baseline",
    EvaluationArchitectureMode.ADOPT_DOC_ONLY_RAG: "Adopt Off-the-Shelf Text-Only RAG",
    EvaluationArchitectureMode.BUILD_GOVERNED_HYBRID_COPILOT: "Governed Hybrid Data Copilot (Ours)",
}


class TableContract(BaseModel):
    """Declarative schema, row-count, null-ratio, and freshness SLA contract for a relational table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_name: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    description: str
    required_columns: list[str] = Field(..., min_length=1)
    timestamp_column: str
    min_rows: int = Field(..., ge=1)
    max_rows: int = Field(..., ge=1)
    max_null_ratio: float = Field(..., ge=0.0, le=1.0)
    warn_staleness_hours: float = Field(..., gt=0.0)
    max_staleness_hours: float = Field(..., gt=0.0)


class TableQualityCheck(BaseModel):
    """Inspection result for a single relational KPI table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_name: str
    status: ReadinessStatus
    row_count: int = Field(..., ge=0)
    latest_refresh_utc: str | None
    staleness_hours: float = Field(..., ge=0.0)
    max_null_ratio_observed: float = Field(..., ge=0.0, le=1.0)
    null_ratios_by_column: dict[str, float]
    missing_columns: list[str]
    schema_valid: bool
    table_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    reasons: list[str]


class DataReadinessReport(BaseModel):
    """Structured pre-execution data freshness and quality gate report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of_utc: str
    overall_status: ReadinessStatus
    can_execute_queries: bool
    database_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    tables: list[TableQualityCheck]
    healthy_tables: list[str]
    warning_tables: list[str]
    blocked_tables: list[str]


class OperationalPassage(BaseModel):
    """Unstructured operational SOP, SLA, or vendor policy section."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passage_id: str = Field(..., min_length=4, max_length=100)
    doc_id: str = Field(..., min_length=4, max_length=80)
    title: str
    category: str
    section_heading: str
    effective_date: str
    text: str
    sha256_digest: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class ScoredPassage(BaseModel):
    """Retrieved operational document passage with hybrid lexical + semantic scores."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passage_id: str
    doc_id: str
    title: str
    category: str
    section_heading: str
    effective_date: str
    text: str
    sha256_digest: str
    lexical_bm25_score: float
    semantic_score: float
    hybrid_score: float
    rank: int = Field(..., ge=1)


class SQLExecutionArtifact(BaseModel):
    """Read-only, AST-validated SQL execution plan and deterministic result snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str
    sql_query: str
    parameters: dict[str, str | int | float]
    target_tables: list[str]
    ast_validated_read_only: bool
    ast_validation_notes: str
    row_count: int = Field(..., ge=0)
    rows: list[dict[str, Any]]
    sql_snapshot_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class NumericTokenCheck(BaseModel):
    """Single numeric/currency/percentage token extracted from a drafted summary and verified."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_token: str
    normalized_value: float
    token_kind: str
    matched_source: str | None = None
    matched_reference: str | None = None
    expected_exact_value: float | None = None
    absolute_diff: float = 0.0
    is_verified: bool


class NumericalVerificationReport(BaseModel):
    """Deterministic numerical grounding verification result over a drafted response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    all_numbers_verified: bool
    total_numeric_tokens: int = Field(..., ge=0)
    verified_tokens: int = Field(..., ge=0)
    unverified_tokens: list[str]
    numerical_parity_rate: float = Field(..., ge=0.0, le=1.0)
    checks: list[NumericTokenCheck]


class CopilotQueryRequest(BaseModel):
    """API request payload for the Enterprise Hybrid Data Copilot."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=5, max_length=600)
    as_of_utc: str = Field(default="2026-10-27T12:00:00Z")
    create_hitl_workflow: bool = Field(default=False)
    auto_submit_for_approval: bool = Field(default=False)

    @field_validator("question")
    @classmethod
    def _validate_safe_question(cls, value: str) -> str:
        return _reject_unsafe_text(value, "question")


class CopilotQueryResponse(BaseModel):
    """Complete decision-support response with freshness gate, SQL/RAG evidence, and numerical verification."""

    model_config = ConfigDict(extra="forbid")

    query_id: str
    question: str
    as_of_utc: str
    route_modality: RouteModality
    data_readiness: DataReadinessReport
    blocked_by_freshness_gate: bool
    blocked_reason: str | None = None
    sql_artifact: SQLExecutionArtifact | None = None
    retrieved_passages: list[ScoredPassage]
    draft_answer: str
    numerical_verification: NumericalVerificationReport
    composite_evidence_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    workflow_id: str | None = None
    workflow_state: WorkflowState | None = None


class AuditLogEntry(BaseModel):
    """Immutable state-transition log entry for HITL workflow approvals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp_utc: str
    from_state: str
    to_state: str
    actor: str
    note: str
    bound_evidence_sha256: str


class HITLWorkflowRecord(BaseModel):
    """Transactional SQLite record for the DRAFT -> PENDING_APPROVAL -> APPROVED / REJECTED state machine."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    question: str
    route_modality: RouteModality
    draft_answer: str
    sql_template_id: str | None
    sql_snapshot_sha256: str
    passage_ids: list[str]
    passage_digests: dict[str, str]
    answer_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    composite_evidence_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    numerical_parity_rate: float = Field(..., ge=0.0, le=1.0)
    state: WorkflowState
    reviewer_id: str | None = None
    reviewer_notes: str | None = None
    created_at_utc: str
    updated_at_utc: str
    audit_trail: list[AuditLogEntry]


class WorkflowCreateRequest(BaseModel):
    """Create a new HITL workflow in DRAFT state."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=5, max_length=600)
    route_modality: RouteModality
    draft_answer: str = Field(..., min_length=5, max_length=4000)
    sql_template_id: str | None = None
    sql_snapshot_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    passage_ids: list[str] = Field(default_factory=list)
    passage_digests: dict[str, str] = Field(default_factory=dict)
    numerical_parity_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    submit_immediately: bool = Field(default=True)

    @field_validator("question", "draft_answer")
    @classmethod
    def _validate_safe_create_fields(cls, value: str) -> str:
        return _reject_unsafe_text(value, "WorkflowCreateRequest field")


class WorkflowTransitionRequest(BaseModel):
    """Transition a workflow from DRAFT -> PENDING_APPROVAL or PENDING_APPROVAL -> APPROVED / REJECTED."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(..., min_length=4, max_length=80)
    target_state: WorkflowState
    expected_evidence_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    actor: str = Field(..., min_length=2, max_length=80)
    notes: str = Field(default="", max_length=500)

    @field_validator("actor", "notes")
    @classmethod
    def _validate_safe_transition_fields(cls, value: str) -> str:
        return _reject_unsafe_text(value, "WorkflowTransitionRequest field")


class WorkflowVerifyDigestRequest(BaseModel):
    """Verify that an APPROVED workflow's SQL snapshot and passage SHA-256 digests have not drifted."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    current_sql_snapshot_sha256: str | None = None
    current_passage_digests: dict[str, str] | None = None


class WorkflowVerifyDigestResponse(BaseModel):
    """Result of verifying an approved HITL workflow against live SQL and document hashes."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    previous_state: WorkflowState
    current_state: WorkflowState
    stored_evidence_sha256: str
    recomputed_evidence_sha256: str
    digest_matches: bool
    drift_reasons: list[str]
    record: HITLWorkflowRecord


class CopilotEvalCase(BaseModel):
    """Single decision-support benchmark query in the 40-case evaluation suite."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(..., pattern=r"^QRY-\d{3}$")
    category: str
    question: str
    as_of_utc: str = "2026-10-27T12:00:00Z"
    expected_modality: RouteModality
    expected_sql_template_id: str | None = None
    expected_target_tables: list[str] = Field(default_factory=list)
    expected_passage_ids: list[str] = Field(default_factory=list)
    expect_freshness_block: bool = False
    expected_numbers: list[float] = Field(default_factory=list)
    reference_summary: str


class CopilotEvalDatasetFile(BaseModel):
    """Top-level wrapper for data/benchmark/copilot_eval_cases.json."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_name: str
    schema_version: str
    default_as_of_utc: str
    description: str
    cases: list[CopilotEvalCase] = Field(..., min_length=40, max_length=40)


class CaseEvalResult(BaseModel):
    """Per-query evaluation trace for a single architecture mode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    category: str
    question: str
    expected_modality: RouteModality
    actual_modality: RouteModality
    routing_correct: bool
    sql_execution_accurate: bool
    numerical_parity_rate: float
    freshness_gate_correct: bool
    latency_ms: float
    estimated_tokens: int
    evidence_sha256: str


class ArchitectureBenchmarkMetrics(BaseModel):
    """Aggregated Build-vs-Adopt evaluation metrics for one architecture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    architecture: EvaluationArchitectureMode
    architecture_label: str
    total_queries: int = Field(..., ge=1)
    SQL_Execution_Accuracy: float = Field(..., ge=0.0, le=1.0)
    Numerical_Parity_Rate: float = Field(..., ge=0.0, le=1.0)
    Freshness_Gate_Precision: float = Field(..., ge=0.0, le=1.0)
    Freshness_Gate_Recall: float = Field(..., ge=0.0, le=1.0)
    Routing_Modality_Accuracy: float = Field(..., ge=0.0, le=1.0)
    Mean_Latency_ms: float = Field(..., ge=0.0)
    Estimated_Tokens_Per_Query: int = Field(..., ge=0)
    Estimated_Token_Cost_USD_Per_1k_Queries: float = Field(..., ge=0.0)


class CopilotBenchmarkReport(BaseModel):
    """Machine-readable Build-vs-Adopt benchmark report saved at artifacts/copilot_benchmark.json."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0.0"
    benchmark_name: str = "enterprise-hybrid-data-copilot-40query-benchmark"
    generated_at_utc: str
    as_of_utc: str
    dataset_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    database_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    corpus_sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    total_queries: int = 40
    total_relational_tables: int
    total_operational_passages: int
    architectures: dict[str, ArchitectureBenchmarkMetrics]
    build_vs_adopt_recommendation: dict[str, Any]
    per_architecture_case_results: dict[str, list[CaseEvalResult]]
