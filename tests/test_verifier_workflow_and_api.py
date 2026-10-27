"""Tests for Numerical Grounding Guardrail, HITL State Machine, Benchmark CLI, and FastAPI."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from copilot.api import CopilotRuntime, create_app
from copilot.evaluate import main as evaluate_cli_main
from copilot.evaluate import run_copilot_benchmark
from copilot.router import HybridDataCopilotRouter
from copilot.schemas import (
    EvaluationArchitectureMode,
    RouteModality,
    WorkflowCreateRequest,
    WorkflowState,
    WorkflowTransitionRequest,
)
from copilot.verifier import verify_numerical_grounding
from copilot.workflow import HITLWorkflowManager


def test_numerical_grounding_verifier_passes_exact_and_flags_hallucinated_numbers() -> None:
    router = HybridDataCopilotRouter()
    res = router.route_and_execute(
        "What was the revenue, actual OPEX, OPEX variance percentage, and gross margin percentage for Zone_DACH_Diagnostics in 2026-Q3?"
    )

    valid_report = verify_numerical_grounding(
        res.draft_answer,
        res.sql_artifact,
        res.retrieved_passages,
        res.readiness_report,
    )
    assert valid_report.all_numbers_verified is True
    assert valid_report.numerical_parity_rate == 1.0
    assert valid_report.unverified_tokens == []

    # Inject a fabricated revenue figure (EUR 99,500,000) not present in SQL result set
    corrupted_summary = (
        "In 2026-Q3, Zone_DACH_Diagnostics recorded EUR 99,500,000 revenue and 64.2% gross margin."
    )
    bad_report = verify_numerical_grounding(
        corrupted_summary,
        res.sql_artifact,
        res.retrieved_passages,
        res.readiness_report,
    )
    assert bad_report.all_numbers_verified is False
    assert bad_report.numerical_parity_rate == 0.5
    assert any("99,500,000" in tok for tok in bad_report.unverified_tokens)


def test_hitl_workflow_state_machine_and_snapshot_drift_invalidation(tmp_path: Path) -> None:
    mgr = HITLWorkflowManager(db_path=tmp_path / "workflows.sqlite")

    wf = mgr.create_workflow(
        WorkflowCreateRequest(
            question="Which zone triggered the FIN-CAP-8PCT CFO Discretionary Spend Freeze in 2026-Q3?",
            route_modality=RouteModality.HYBRID_MULTI_SOURCE,
            draft_answer="Zone_US_East_Robotics recorded 14.0% OPEX variance (>8.0% FIN-CAP-8PCT cap).",
            sql_template_id="tpl_zone_fin_all",
            sql_snapshot_sha256="a" * 64,
            passage_ids=["SOP-FIN-202#S1"],
            passage_digests={"SOP-FIN-202#S1": "b" * 64},
            numerical_parity_rate=1.0,
            submit_immediately=False,
        )
    )
    assert wf.state == WorkflowState.DRAFT

    # Illegal direct transition DRAFT -> APPROVED must be rejected
    with pytest.raises(ValueError, match="Invalid state transition"):
        mgr.transition(
            WorkflowTransitionRequest(
                workflow_id=wf.workflow_id,
                target_state=WorkflowState.APPROVED,
                expected_evidence_sha256=wf.composite_evidence_sha256,
                actor="cfo@enterprise.local",
            )
        )

    # Valid transition DRAFT -> PENDING_APPROVAL
    pending = mgr.transition(
        WorkflowTransitionRequest(
            workflow_id=wf.workflow_id,
            target_state=WorkflowState.PENDING_APPROVAL,
            expected_evidence_sha256=wf.composite_evidence_sha256,
            actor="analyst@enterprise.local",
            notes="Ready for CFO sign-off",
        )
    )
    assert pending.state == WorkflowState.PENDING_APPROVAL

    # Valid transition PENDING_APPROVAL -> APPROVED
    approved = mgr.transition(
        WorkflowTransitionRequest(
            workflow_id=wf.workflow_id,
            target_state=WorkflowState.APPROVED,
            expected_evidence_sha256=wf.composite_evidence_sha256,
            actor="cfo@enterprise.local",
            notes="Approved spend freeze action",
        )
    )
    assert approved.state == WorkflowState.APPROVED
    assert len(approved.audit_trail) == 3

    # Verify with unchanged SQL snapshot remains APPROVED
    ver_ok = mgr.verify_digest(
        wf.workflow_id,
        current_sql_snapshot_sha256="a" * 64,
        current_passage_digests={"SOP-FIN-202#S1": "b" * 64},
    )
    assert ver_ok.digest_matches is True
    assert ver_ok.current_state == WorkflowState.APPROVED

    # Simulate SQL snapshot drift -> automatically invalidates approval to REJECTED!
    ver_drift = mgr.verify_digest(
        wf.workflow_id,
        current_sql_snapshot_sha256="c" * 64,
        current_passage_digests={"SOP-FIN-202#S1": "b" * 64},
    )
    assert ver_drift.digest_matches is False
    assert ver_drift.previous_state == WorkflowState.APPROVED
    assert ver_drift.current_state == WorkflowState.REJECTED
    assert any("SQL snapshot SHA-256 drifted" in r for r in ver_drift.drift_reasons)


def test_40_query_build_vs_adopt_benchmark_and_cli_check() -> None:
    report = run_copilot_benchmark()
    assert report.total_queries == 40
    assert report.total_relational_tables == 4
    assert report.total_operational_passages == 16

    ours = report.architectures[EvaluationArchitectureMode.BUILD_GOVERNED_HYBRID_COPILOT.value]
    sql_base = report.architectures[EvaluationArchitectureMode.UNGOVERNED_PROMPT_SQL.value]
    rag_base = report.architectures[EvaluationArchitectureMode.ADOPT_DOC_ONLY_RAG.value]

    assert ours.SQL_Execution_Accuracy == 1.0
    assert ours.Numerical_Parity_Rate == 1.0
    assert ours.Freshness_Gate_Precision == 1.0
    assert ours.Routing_Modality_Accuracy == 1.0
    assert ours.Numerical_Parity_Rate > sql_base.Numerical_Parity_Rate
    assert ours.Numerical_Parity_Rate > rag_base.Numerical_Parity_Rate
    assert ours.Estimated_Tokens_Per_Query < sql_base.Estimated_Tokens_Per_Query

    assert evaluate_cli_main(["--check"]) == 0


def test_fastapi_endpoints_and_console_ui() -> None:
    rt = CopilotRuntime(workflow_db_path=":memory:")
    client = TestClient(create_app(rt))

    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["governance"]["numerical_grounding_verifier"] is True

    r = client.get("/api/readiness")
    assert r.status_code == 200
    assert "legacy_supply_backlog_partition" in r.json()["blocked_tables"]

    b = client.get("/api/benchmark")
    assert b.status_code == 200
    assert b.json()["total_queries"] == 40

    q = client.post(
        "/api/query",
        json={
            "question": "Why was supplier VND-LOG-03 assessed a EUR 64,800 penalty rebate in 2026-Q3 under clause VND-SLA-995?",
            "as_of_utc": "2026-10-27T12:00:00Z",
            "create_hitl_workflow": True,
            "auto_submit_for_approval": True,
        },
    )
    assert q.status_code == 200
    q_data = q.json()
    assert q_data["route_modality"] == "hybrid_multi_source"
    assert q_data["numerical_verification"]["all_numbers_verified"] is True
    assert q_data["workflow_state"] == "PENDING_APPROVAL"

    wf_id = q_data["workflow_id"]
    ev_sha = q_data["composite_evidence_sha256"]

    tr = client.post(
        "/api/workflows/transition",
        json={
            "workflow_id": wf_id,
            "target_state": "APPROVED",
            "expected_evidence_sha256": ev_sha,
            "actor": "vp-procurement@enterprise.local",
            "notes": "Verified penalty rebate calculation",
        },
    )
    assert tr.status_code == 200
    assert tr.json()["state"] == "APPROVED"

    vd = client.post(
        "/api/workflows/verify-digest",
        json={
            "workflow_id": wf_id,
            "current_sql_snapshot_sha256": "0" * 64,
        },
    )
    assert vd.status_code == 200
    assert vd.json()["current_state"] == "REJECTED"

    root = client.get("/")
    assert root.status_code == 200
    assert "Enterprise Hybrid Data Copilot" in root.text
