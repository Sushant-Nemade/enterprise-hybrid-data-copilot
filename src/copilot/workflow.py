"""Human-in-the-Loop (HITL) Approval & Audit Trail State Machine (`src/copilot/workflow.py`).

Implements a transactional SQLite approval state machine:
  DRAFT -> PENDING_APPROVAL -> APPROVED / REJECTED
Binds approvals to the composite SHA-256 hash of the SQL snapshot and retrieved passages,
and automatically transitions APPROVED records to REJECTED if upstream SQL or document
hashes drift.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from copilot.datasets import sha256_hex
from copilot.schemas import (
    AuditLogEntry,
    HITLWorkflowRecord,
    RouteModality,
    WorkflowCreateRequest,
    WorkflowState,
    WorkflowTransitionRequest,
    WorkflowVerifyDigestResponse,
)

EMPTY_SQL_SHA256 = sha256_hex("NO_SQL_SNAPSHOT")

ALLOWED_STATE_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.DRAFT: {WorkflowState.PENDING_APPROVAL, WorkflowState.REJECTED},
    WorkflowState.PENDING_APPROVAL: {WorkflowState.APPROVED, WorkflowState.REJECTED},
    WorkflowState.APPROVED: {WorkflowState.REJECTED},
    WorkflowState.REJECTED: set(),
}


def compute_composite_evidence_sha256(
    question: str,
    sql_snapshot_sha256: str,
    passage_digests: dict[str, str],
    draft_answer: str,
) -> str:
    """Compute SHA256(normalized_question || sql_snapshot_sha256 || sorted_passage_sha256s || answer_sha256)."""
    q_norm = re.sub(r"\s+", " ", question.strip().lower())
    sorted_passages = "|".join(
        f"{pid}:{passage_digests[pid]}" for pid in sorted(passage_digests.keys())
    )
    ans_sha = sha256_hex(draft_answer.strip())
    payload = (
        f"question={q_norm}||sql_sha256={sql_snapshot_sha256}||"
        f"passages={sorted_passages}||answer_sha256={ans_sha}"
    )
    return sha256_hex(payload)


class HITLWorkflowManager:
    """Transactional SQLite state machine for digest-bound HITL workflow approvals."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hitl_workflows (
                    workflow_id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    route_modality TEXT NOT NULL,
                    draft_answer TEXT NOT NULL,
                    sql_template_id TEXT,
                    sql_snapshot_sha256 TEXT NOT NULL,
                    passage_ids_json TEXT NOT NULL,
                    passage_digests_json TEXT NOT NULL,
                    answer_sha256 TEXT NOT NULL,
                    composite_evidence_sha256 TEXT NOT NULL,
                    numerical_parity_rate REAL NOT NULL,
                    state TEXT NOT NULL,
                    reviewer_id TEXT,
                    reviewer_notes TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    audit_trail_json TEXT NOT NULL
                );
                """
            )

    def _row_to_record(self, row: sqlite3.Row) -> HITLWorkflowRecord:
        raw_audit = json.loads(str(row["audit_trail_json"]))
        return HITLWorkflowRecord(
            workflow_id=str(row["workflow_id"]),
            question=str(row["question"]),
            route_modality=RouteModality(str(row["route_modality"])),
            draft_answer=str(row["draft_answer"]),
            sql_template_id=str(row["sql_template_id"]) if row["sql_template_id"] is not None else None,
            sql_snapshot_sha256=str(row["sql_snapshot_sha256"]),
            passage_ids=json.loads(str(row["passage_ids_json"])),
            passage_digests=json.loads(str(row["passage_digests_json"])),
            answer_sha256=str(row["answer_sha256"]),
            composite_evidence_sha256=str(row["composite_evidence_sha256"]),
            numerical_parity_rate=float(row["numerical_parity_rate"]),
            state=WorkflowState(str(row["state"])),
            reviewer_id=str(row["reviewer_id"]) if row["reviewer_id"] is not None else None,
            reviewer_notes=str(row["reviewer_notes"]) if row["reviewer_notes"] is not None else None,
            created_at_utc=str(row["created_at_utc"]),
            updated_at_utc=str(row["updated_at_utc"]),
            audit_trail=[AuditLogEntry.model_validate(entry) for entry in raw_audit],
        )

    def create_workflow(self, req: WorkflowCreateRequest) -> HITLWorkflowRecord:
        """Create a workflow in DRAFT state (and optionally transition to PENDING_APPROVAL)."""
        workflow_id = f"WF-{uuid.uuid4().hex[:10].upper()}"
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ans_sha = sha256_hex(req.draft_answer.strip())
        comp_sha = compute_composite_evidence_sha256(
            req.question,
            req.sql_snapshot_sha256,
            req.passage_digests,
            req.draft_answer,
        )

        initial_audit = [
            AuditLogEntry(
                timestamp_utc=now_utc,
                from_state="INIT",
                to_state=WorkflowState.DRAFT.value,
                actor="system:hybrid-data-copilot",
                note="Created digest-bound decision-support draft.",
                bound_evidence_sha256=comp_sha,
            ).model_dump(mode="json")
        ]

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO hitl_workflows VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?
                );
                """,
                (
                    workflow_id,
                    req.question,
                    req.route_modality.value,
                    req.draft_answer,
                    req.sql_template_id,
                    req.sql_snapshot_sha256,
                    json.dumps(req.passage_ids),
                    json.dumps(req.passage_digests, sort_keys=True),
                    ans_sha,
                    comp_sha,
                    req.numerical_parity_rate,
                    WorkflowState.DRAFT.value,
                    now_utc,
                    now_utc,
                    json.dumps(initial_audit),
                ),
            )

        if req.submit_immediately:
            return self.transition(
                WorkflowTransitionRequest(
                    workflow_id=workflow_id,
                    target_state=WorkflowState.PENDING_APPROVAL,
                    expected_evidence_sha256=comp_sha,
                    actor="system:auto-submit",
                    notes="Submitted to PENDING_APPROVAL queue for executive review.",
                )
            )
        return self.get(workflow_id)

    def get(self, workflow_id: str) -> HITLWorkflowRecord:
        row = self._conn.execute(
            "SELECT * FROM hitl_workflows WHERE workflow_id = ?;",
            (workflow_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Workflow {workflow_id!r} not found")
        return self._row_to_record(row)

    def list_workflows(self, state: WorkflowState | None = None) -> list[HITLWorkflowRecord]:
        if state is not None:
            rows = self._conn.execute(
                "SELECT * FROM hitl_workflows WHERE state = ? ORDER BY updated_at_utc DESC, workflow_id ASC;",
                (state.value,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM hitl_workflows ORDER BY updated_at_utc DESC, workflow_id ASC;"
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def transition(self, req: WorkflowTransitionRequest) -> HITLWorkflowRecord:
        """Execute a validated state transition (DRAFT -> PENDING_APPROVAL -> APPROVED / REJECTED)."""
        record = self.get(req.workflow_id)

        if record.composite_evidence_sha256 != req.expected_evidence_sha256:
            raise ValueError(
                f"Evidence SHA-256 mismatch for {req.workflow_id}: expected "
                f"{req.expected_evidence_sha256}, stored {record.composite_evidence_sha256}"
            )

        allowed_targets = ALLOWED_STATE_TRANSITIONS.get(record.state, set())
        if req.target_state not in allowed_targets:
            raise ValueError(
                f"Invalid state transition {record.state.value} -> {req.target_state.value}. "
                f"Allowed targets from {record.state.value}: {[s.value for s in sorted(allowed_targets, key=lambda x: x.value)]}"
            )

        if req.target_state == WorkflowState.APPROVED and record.numerical_parity_rate < 1.0:
            raise ValueError(
                f"Cannot transition {req.workflow_id} to APPROVED: numerical_parity_rate="
                f"{record.numerical_parity_rate:.4f} < 1.0 (NUM-PARITY-100)."
            )

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        audit_list = [e.model_dump(mode="json") for e in record.audit_trail]
        audit_list.append(
            AuditLogEntry(
                timestamp_utc=now_utc,
                from_state=record.state.value,
                to_state=req.target_state.value,
                actor=req.actor,
                note=req.notes or f"Transitioned to {req.target_state.value}.",
                bound_evidence_sha256=record.composite_evidence_sha256,
            ).model_dump(mode="json")
        )

        reviewer_id = req.actor if req.target_state in (WorkflowState.APPROVED, WorkflowState.REJECTED) else record.reviewer_id
        reviewer_notes = req.notes if req.target_state in (WorkflowState.APPROVED, WorkflowState.REJECTED) else record.reviewer_notes

        with self._conn:
            self._conn.execute(
                """
                UPDATE hitl_workflows
                   SET state = ?,
                       reviewer_id = ?,
                       reviewer_notes = ?,
                       updated_at_utc = ?,
                       audit_trail_json = ?
                 WHERE workflow_id = ?;
                """,
                (
                    req.target_state.value,
                    reviewer_id,
                    reviewer_notes,
                    now_utc,
                    json.dumps(audit_list),
                    req.workflow_id,
                ),
            )
        return self.get(req.workflow_id)

    def verify_digest(
        self,
        workflow_id: str,
        current_sql_snapshot_sha256: str | None = None,
        current_passage_digests: dict[str, str] | None = None,
    ) -> WorkflowVerifyDigestResponse:
        """Verify an existing workflow against live SQL snapshot and passage SHA-256 digests."""
        record = self.get(workflow_id)
        prev_state = record.state
        active_sql_sha = (
            current_sql_snapshot_sha256
            if current_sql_snapshot_sha256 is not None
            else record.sql_snapshot_sha256
        )

        drift_reasons: list[str] = []
        if active_sql_sha != record.sql_snapshot_sha256:
            drift_reasons.append(
                f"SQL snapshot SHA-256 drifted from {record.sql_snapshot_sha256[:12]}... to {active_sql_sha[:12]}..."
            )

        active_passages: dict[str, str] = {}
        for pid, orig_sha in record.passage_digests.items():
            live_sha = (
                current_passage_digests.get(pid, orig_sha)
                if current_passage_digests is not None
                else orig_sha
            )
            active_passages[pid] = live_sha
            if live_sha != orig_sha:
                drift_reasons.append(f"Passage {pid} SHA-256 drifted.")

        recomputed_sha = compute_composite_evidence_sha256(
            record.question,
            active_sql_sha,
            active_passages,
            record.draft_answer,
        )
        matches = (recomputed_sha == record.composite_evidence_sha256) and not drift_reasons

        if not matches and record.state in (WorkflowState.APPROVED, WorkflowState.PENDING_APPROVAL):
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            audit_list = [e.model_dump(mode="json") for e in record.audit_trail]
            reason_note = "invalidated_by_data_drift: " + "; ".join(drift_reasons)
            audit_list.append(
                AuditLogEntry(
                    timestamp_utc=now_utc,
                    from_state=record.state.value,
                    to_state=WorkflowState.REJECTED.value,
                    actor="system:digest-verifier",
                    note=reason_note,
                    bound_evidence_sha256=recomputed_sha,
                ).model_dump(mode="json")
            )
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE hitl_workflows
                       SET state = ?,
                           reviewer_notes = ?,
                           updated_at_utc = ?,
                           audit_trail_json = ?
                     WHERE workflow_id = ?;
                    """,
                    (
                        WorkflowState.REJECTED.value,
                        reason_note,
                        now_utc,
                        json.dumps(audit_list),
                        workflow_id,
                    ),
                )
            record = self.get(workflow_id)

        return WorkflowVerifyDigestResponse(
            workflow_id=workflow_id,
            previous_state=prev_state,
            current_state=record.state,
            stored_evidence_sha256=record.composite_evidence_sha256,
            recomputed_evidence_sha256=recomputed_sha,
            digest_matches=matches,
            drift_reasons=drift_reasons,
            record=record,
        )
