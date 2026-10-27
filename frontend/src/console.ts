/**
 * Typed Decision-Support Review Console Controller (TypeScript).
 * Powers the 4 interactive tabs of Enterprise Hybrid Data Copilot:
 *   1. Build-vs-Adopt 40-Query Evaluation Benchmark
 *   2. Data Freshness & Quality Gate Inspector
 *   3. Semantic SQL + Unstructured SOP Hybrid Router & Numerical Verifier
 *   4. Digest-Bound HITL Approval State Machine (DRAFT -> PENDING_APPROVAL -> APPROVED / REJECTED)
 */

export interface ArchitectureMetrics {
  architecture: string;
  architecture_label: string;
  total_queries: number;
  SQL_Execution_Accuracy: number;
  Numerical_Parity_Rate: number;
  Freshness_Gate_Precision: number;
  Freshness_Gate_Recall: number;
  Routing_Modality_Accuracy: number;
  Mean_Latency_ms: number;
  Estimated_Tokens_Per_Query: number;
  Estimated_Token_Cost_USD_Per_1k_Queries: number;
}

export interface TableQualityCheck {
  table_name: string;
  status: "ready" | "warn_stale" | "blocked_stale" | "blocked_contract";
  row_count: number;
  latest_refresh_utc: string | null;
  staleness_hours: number;
  max_null_ratio_observed: number;
  schema_valid: boolean;
  table_sha256: string;
  reasons: string[];
}

export interface NumericTokenCheck {
  raw_token: string;
  normalized_value: number;
  token_kind: string;
  matched_source: string | null;
  matched_reference: string | null;
  expected_exact_value: number | null;
  absolute_diff: number;
  is_verified: boolean;
}

export interface HITLAuditEntry {
  timestamp_utc: string;
  from_state: string;
  to_state: string;
  actor: string;
  note: string;
  bound_evidence_sha256: string;
}

export interface HITLWorkflowStateModel {
  workflow_id: string;
  question: string;
  route_modality: string;
  draft_answer: string;
  sql_template_id: string | null;
  original_sql_sha256: string;
  current_sql_sha256: string;
  stored_evidence_sha256: string;
  recomputed_evidence_sha256: string;
  numerical_parity_rate: number;
  state: "DRAFT" | "PENDING_APPROVAL" | "APPROVED" | "REJECTED";
  audit_trail: HITLAuditEntry[];
}
