"""Consumer path: optimize → same-plan fiscal reconcile (capital coefficients)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from landmark_field_network.examples import build_toy_field
from landmark_field_network.export import economics_project_list
from landmark_field_network.master import optimize_portfolio

pytest.importorskip("sqlalchemy")
pytest.importorskip("landmark_economics")

from landmark_field_network.reconcile import reconcile_plan  # noqa: E402


def test_optimize_plan_reconciles_through_landmark_economics() -> None:
    model = build_toy_field()
    opt = optimize_portfolio(model, method="integrated")
    assert opt.plan.starts, "optimizer must select at least one start"
    report = reconcile_plan(model, opt.plan, opt.network, case_id="toy_optimize_reconcile")
    assert report.engine == "landmark_economics"
    assert report.portfolio_npv_fiscal != 0.0
    assert any(p.npv_fiscal != 0.0 for p in report.projects)


def test_optimize_export_and_reconcile_out_share_one_plan(tmp_path: Path) -> None:
    model = build_toy_field()
    opt = optimize_portfolio(model, method="integrated")
    handoff = economics_project_list(model, opt.plan, opt.network, case_id="toy_shared")
    handoff_path = tmp_path / "handoff.json"
    handoff.write_json(handoff_path)
    report = reconcile_plan(model, opt.plan, opt.network, case_id="toy_shared")
    reconcile_path = tmp_path / "reconcile.json"
    reconcile_path.write_text(json.dumps(report.to_dict(), indent=2))

    handoff_payload = json.loads(handoff_path.read_text())
    handoff_ids = {
        p.get("project_id") or p.get("id") for p in handoff_payload.get("projects", [])
    }
    # Facilities may live under facility_starts in the handoff.
    handoff_ids |= {
        p.get("project_id") or p.get("id")
        for p in handoff_payload.get("facility_starts", [])
    }
    reconcile_ids = {p["project_id"] for p in report.to_dict()["projects"]}
    plan_ids = {s.project_id for s in opt.plan.starts}
    assert reconcile_ids <= plan_ids
    assert handoff_ids & plan_ids
    assert report.engine == "landmark_economics"
    assert reconcile_path.is_file()
