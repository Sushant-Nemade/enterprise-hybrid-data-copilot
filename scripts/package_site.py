"""Package static benchmark and interactive scenario bundle into src/copilot/site/data/."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from copilot.api import CopilotRuntime, create_app
from copilot.evaluate import DEFAULT_REPORT_PATH, run_copilot_benchmark
from copilot.schemas import CopilotQueryRequest

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA_DIR = ROOT / "src" / "copilot" / "site" / "data"


def build_site_data() -> None:
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    rt = CopilotRuntime()

    if DEFAULT_REPORT_PATH.is_file():
        bench_text = DEFAULT_REPORT_PATH.read_text(encoding="utf-8")
    else:
        report = run_copilot_benchmark()
        bench_text = json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
        DEFAULT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_REPORT_PATH.write_text(bench_text, encoding="utf-8")

    (SITE_DATA_DIR / "copilot_benchmark.json").write_text(bench_text, encoding="utf-8")

    client = TestClient(create_app(rt))
    readiness_default = client.get("/api/readiness?as_of_utc=2026-10-27T12:00:00Z").json()
    readiness_future_stale = client.get("/api/readiness?as_of_utc=2026-10-30T12:00:00Z").json()

    showcase_queries = [
        (
            "QRY-027",
            "Hybrid Multi-Source: OPEX Variance vs FIN-CAP-8PCT CFO Spend Freeze",
            "Which zone triggered the FIN-CAP-8PCT CFO Discretionary Spend Freeze in 2026-Q3 based on its OPEX variance percentage, and which zone requires a VP Finance memo?",
            "2026-10-27T12:00:00Z",
        ),
        (
            "QRY-030",
            "Hybrid Multi-Source: Supplier VND-LOG-03 Penalty Rebate vs VND-SLA-995",
            "Why was supplier VND-LOG-03 assessed a EUR 64,800 penalty rebate in 2026-Q3 under clause VND-SLA-995?",
            "2026-10-27T12:00:00Z",
        ),
        (
            "QRY-025",
            "Hybrid Multi-Source: Zone OTD % & Breaches vs OPS-SLA-95 CAPA Gate",
            "Which operational zone violated the OPS-SLA-95 minimum 95.0% on-time delivery or 5-breach cap in 2026-Q3, and what action is required?",
            "2026-10-27T12:00:00Z",
        ),
        (
            "QRY-010",
            "SQL Only (AST-Validated Aggregation): Total Revenue, OPEX & Cloud AI Spend",
            "What is the total revenue, total actual OPEX, and total cloud AI spend in EUR across all zones in 2026-Q3?",
            "2026-10-27T12:00:00Z",
        ),
        (
            "QRY-023",
            "RAG Only (Architecture SOP): Build-vs-Adopt Framework ARCH-BVA-01",
            "According to framework ARCH-BVA-01 and target ARCH-COST-20MS, when should we build a governed hybrid copilot and what is the token reduction target?",
            "2026-10-27T12:00:00Z",
        ),
        (
            "QRY-035",
            "Freshness Gate Block: Stale Legacy Supply Backlog Partition (222.0h > 48.0h)",
            "How many backordered SKUs and blocked orders in EUR are in legacy_supply_backlog_partition for Zone_US_East_Robotics?",
            "2026-10-27T12:00:00Z",
        ),
    ]

    scenarios: list[dict[str, object]] = []
    for cid, label, question, as_of in showcase_queries:
        resp = client.post(
            "/api/query",
            json=CopilotQueryRequest(
                question=question,
                as_of_utc=as_of,
                create_hitl_workflow=False,
            ).model_dump(mode="json"),
        ).json()
        scenarios.append(
            {
                "case_id": cid,
                "label": label,
                "question": question,
                "as_of_utc": as_of,
                "response": resp,
            }
        )

    workflows_seed = client.get("/api/workflows").json()
    bundle = {
        "readiness_default": readiness_default,
        "readiness_future_stale": readiness_future_stale,
        "scenarios": scenarios,
        "workflows_seed": workflows_seed,
    }
    (SITE_DATA_DIR / "console_bundle.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Packaged static console bundle into {SITE_DATA_DIR}")


if __name__ == "__main__":
    build_site_data()
