"""Fiscal reconcile through landmark-economics."""

from __future__ import annotations

from landmark_fieldvet.examples import build_toy_field
from landmark_fieldvet.models import Plan, StartDecision
from landmark_fieldvet.network import solve_network
from landmark_fieldvet.reconcile import reconcile_plan


def test_reconcile_returns_fiscal_npv() -> None:
    model = build_toy_field()
    plan = Plan(
        starts=(
            StartDecision("pad_a", 0),
            StartDecision("pad_b", 0),
            StartDecision("comp_expand", 0),
        )
    )
    network = solve_network(model, plan)
    report = reconcile_plan(model, plan, network, case_id="toy_reconcile")
    assert report.engine == "landmark_economics"
    assert len(report.projects) == 2
    assert report.portfolio_npv_fiscal != 0.0
    assert "landmark-economics" in report.notes
