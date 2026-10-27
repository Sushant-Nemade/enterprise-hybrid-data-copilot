"""FastAPI Backend & Decision-Support Review Console Service (`src/copilot/api.py`)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from copilot import __version__
from copilot.data_quality import evaluate_warehouse_readiness
from copilot.evaluate import DEFAULT_REPORT_PATH, run_copilot_benchmark
from copilot.router import HybridDataCopilotRouter
from copilot.schemas import (
    CopilotBenchmarkReport,
    CopilotQueryRequest,
    CopilotQueryResponse,
    DataReadinessReport,
    HITLWorkflowRecord,
    WorkflowCreateRequest,
    WorkflowState,
    WorkflowTransitionRequest,
    WorkflowVerifyDigestRequest,
    WorkflowVerifyDigestResponse,
)
from copilot.verifier import verify_numerical_grounding
from copilot.workflow import (
    EMPTY_SQL_SHA256,
    HITLWorkflowManager,
    compute_composite_evidence_sha256,
)

SITE_DIR = Path(__file__).resolve().parent / "site"


class CopilotRuntime:
    """Stateful container holding the SQLite warehouse, router, HITL workflow manager, and benchmark."""

    def __init__(self, workflow_db_path: str | Path = ":memory:") -> None:
        self.router = HybridDataCopilotRouter()
        self.workflow_mgr = HITLWorkflowManager(db_path=workflow_db_path)
        self._cached_benchmark: CopilotBenchmarkReport | None = None
        self._seed_initial_workflow()

    def _seed_initial_workflow(self) -> None:
        if self.workflow_mgr.list_workflows():
            return
        q = (
            "Which zone triggered the FIN-CAP-8PCT CFO Discretionary Spend Freeze in 2026-Q3 "
            "based on its OPEX variance percentage, and which zone requires a VP Finance memo?"
        )
        res = self.router.route_and_execute(q, as_of_utc="2026-10-27T12:00:00Z")
        sql_sha = res.sql_artifact.sql_snapshot_sha256 if res.sql_artifact else EMPTY_SQL_SHA256
        p_digests = {p.passage_id: p.sha256_digest for p in res.retrieved_passages}
        self.workflow_mgr.create_workflow(
            WorkflowCreateRequest(
                question=q,
                route_modality=res.modality,
                draft_answer=res.draft_answer,
                sql_template_id=res.sql_artifact.template_id if res.sql_artifact else None,
                sql_snapshot_sha256=sql_sha,
                passage_ids=[p.passage_id for p in res.retrieved_passages],
                passage_digests=p_digests,
                numerical_parity_rate=1.0,
                submit_immediately=True,
            )
        )

    def get_benchmark_report(self) -> CopilotBenchmarkReport:
        if self._cached_benchmark is not None:
            return self._cached_benchmark
        if DEFAULT_REPORT_PATH.is_file():
            self._cached_benchmark = CopilotBenchmarkReport.model_validate_json(
                DEFAULT_REPORT_PATH.read_text(encoding="utf-8")
            )
            return self._cached_benchmark
        self._cached_benchmark = run_copilot_benchmark()
        return self._cached_benchmark


def create_app(runtime: CopilotRuntime | None = None) -> FastAPI:
    """Create the FastAPI application for Enterprise Hybrid Data Copilot."""
    rt = runtime or CopilotRuntime(
        workflow_db_path=os.environ.get("COPILOT_WORKFLOW_DB", ":memory:")
    )

    app = FastAPI(
        title="Enterprise Hybrid Data Copilot",
        version=__version__,
        description=(
            "Bridges structured relational KPIs (SQLite) and unstructured operational documents "
            "with automated data-freshness gates, AST-validated read-only semantic SQL, "
            "deterministic numerical grounding verification, and SHA-256 digest-bound HITL approvals."
        ),
    )
    app.state.runtime = rt

    @app.middleware("http")
    async def add_security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

    @app.get("/api/health", tags=["system"])
    def get_health() -> dict[str, Any]:
        readiness = evaluate_warehouse_readiness(rt.router.connection)
        return {
            "status": "ok",
            "version": __version__,
            "warehouse_overall_status": readiness.overall_status.value,
            "database_sha256": readiness.database_sha256,
            "healthy_tables": readiness.healthy_tables,
            "blocked_tables": readiness.blocked_tables,
            "operational_passages": len(rt.router.passages),
            "governance": {
                "data_freshness_gate": True,
                "ast_read_only_sql": True,
                "numerical_grounding_verifier": True,
                "digest_bound_hitl_state_machine": True,
            },
        }

    @app.get("/api/readiness", response_model=DataReadinessReport, tags=["data-quality"])
    def get_readiness(
        as_of_utc: str = Query(default="2026-10-27T12:00:00Z"),
    ) -> DataReadinessReport:
        return evaluate_warehouse_readiness(rt.router.connection, as_of_utc=as_of_utc)

    @app.get("/api/benchmark", response_model=CopilotBenchmarkReport, tags=["evaluation"])
    def get_benchmark() -> CopilotBenchmarkReport:
        return rt.get_benchmark_report()

    @app.post("/api/query", response_model=CopilotQueryResponse, tags=["copilot"])
    def execute_copilot_query(req: CopilotQueryRequest) -> CopilotQueryResponse:
        routed = rt.router.route_and_execute(req.question, as_of_utc=req.as_of_utc)
        num_ver = verify_numerical_grounding(
            draft_answer=routed.draft_answer,
            sql_artifact=routed.sql_artifact,
            passages=routed.retrieved_passages,
            readiness_report=routed.readiness_report,
        )

        sql_sha = (
            routed.sql_artifact.sql_snapshot_sha256
            if routed.sql_artifact is not None
            else EMPTY_SQL_SHA256
        )
        p_digests = {p.passage_id: p.sha256_digest for p in routed.retrieved_passages}
        comp_sha = compute_composite_evidence_sha256(
            req.question,
            sql_sha,
            p_digests,
            routed.draft_answer,
        )

        wf_id: str | None = None
        wf_state: WorkflowState | None = None
        if req.create_hitl_workflow:
            wf = rt.workflow_mgr.create_workflow(
                WorkflowCreateRequest(
                    question=req.question,
                    route_modality=routed.modality,
                    draft_answer=routed.draft_answer,
                    sql_template_id=(
                        routed.sql_artifact.template_id if routed.sql_artifact else None
                    ),
                    sql_snapshot_sha256=sql_sha,
                    passage_ids=[p.passage_id for p in routed.retrieved_passages],
                    passage_digests=p_digests,
                    numerical_parity_rate=num_ver.numerical_parity_rate,
                    submit_immediately=req.auto_submit_for_approval,
                )
            )
            wf_id = wf.workflow_id
            wf_state = wf.state

        return CopilotQueryResponse(
            query_id=f"COP-{uuid.uuid4().hex[:10].upper()}",
            question=req.question,
            as_of_utc=req.as_of_utc,
            route_modality=routed.modality,
            data_readiness=routed.readiness_report,
            blocked_by_freshness_gate=routed.blocked_by_freshness_gate,
            blocked_reason=routed.blocked_reason,
            sql_artifact=routed.sql_artifact,
            retrieved_passages=routed.retrieved_passages,
            draft_answer=routed.draft_answer,
            numerical_verification=num_ver,
            composite_evidence_sha256=comp_sha,
            workflow_id=wf_id,
            workflow_state=wf_state,
        )

    @app.get("/api/workflows", response_model=list[HITLWorkflowRecord], tags=["hitl-workflow"])
    def list_workflows(
        state: WorkflowState | None = Query(default=None),
    ) -> list[HITLWorkflowRecord]:
        return rt.workflow_mgr.list_workflows(state=state)

    @app.post("/api/workflows", response_model=HITLWorkflowRecord, tags=["hitl-workflow"])
    def create_workflow(req: WorkflowCreateRequest) -> HITLWorkflowRecord:
        return rt.workflow_mgr.create_workflow(req)

    @app.post("/api/workflows/transition", response_model=HITLWorkflowRecord, tags=["hitl-workflow"])
    def transition_workflow(req: WorkflowTransitionRequest) -> HITLWorkflowRecord:
        try:
            return rt.workflow_mgr.transition(req)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/workflows/verify-digest",
        response_model=WorkflowVerifyDigestResponse,
        tags=["hitl-workflow"],
    )
    def verify_workflow_digest(req: WorkflowVerifyDigestRequest) -> WorkflowVerifyDigestResponse:
        try:
            return rt.workflow_mgr.verify_digest(
                workflow_id=req.workflow_id,
                current_sql_snapshot_sha256=req.current_sql_snapshot_sha256,
                current_passage_digests=req.current_passage_digests,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    if SITE_DIR.is_dir():
        data_sub = SITE_DIR / "data"
        if data_sub.is_dir():
            app.mount("/data", StaticFiles(directory=data_sub), name="site-data")

        @app.get("/", include_in_schema=False)
        def serve_console_index() -> FileResponse:
            return FileResponse(SITE_DIR / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def serve_fallback_root() -> JSONResponse:
            return JSONResponse({"service": "enterprise-hybrid-data-copilot", "version": __version__})

    return app


app = create_app()
