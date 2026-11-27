"""Integrated MILP is the reference; Benders must match NPV within tolerance."""

from __future__ import annotations

from landmark_fieldvet.examples import build_dual_bottleneck, build_toy_field
from landmark_fieldvet.master import optimize_portfolio
from landmark_fieldvet.network import solve_network

ABS_TOL = 1.0
REL_TOL = 1e-3


def _npv_close(a: float, b: float) -> bool:
    return abs(a - b) <= max(ABS_TOL, REL_TOL * max(1.0, abs(a), abs(b)))


def test_benders_matches_integrated_on_toy() -> None:
    model = build_toy_field()
    integ = optimize_portfolio(model, method="integrated")
    bend = optimize_portfolio(model, method="benders", abs_tol=ABS_TOL, rel_tol=REL_TOL)
    assert _npv_close(integ.objective, bend.objective)
    # Both plans must be feasible network optima for their starts.
    assert _npv_close(integ.objective, solve_network(model, integ.plan).objective)
    assert _npv_close(bend.objective, solve_network(model, bend.plan).objective)
    assert bend.stats is not None
    assert bend.stats.iterations >= 1
    assert bend.stats.converged


def test_benders_matches_integrated_on_dual_bottleneck() -> None:
    model = build_dual_bottleneck(n_periods=12, n_pads=4)
    integ = optimize_portfolio(model, method="integrated")
    bend = optimize_portfolio(
        model,
        method="benders",
        abs_tol=ABS_TOL,
        rel_tol=REL_TOL,
        time_limit_sec=60.0,
    )
    assert _npv_close(integ.objective, bend.objective)
    assert bend.stats is not None
    assert bend.stats.converged

    # If schedules differ, both must be feasible and near-optimal (ties allowed).
    integ_ids = {s.project_id for s in integ.plan.starts}
    bend_ids = {s.project_id for s in bend.plan.starts}
    if integ_ids != bend_ids or integ.plan.start_map() != bend.plan.start_map():
        assert _npv_close(
            solve_network(model, integ.plan).objective,
            solve_network(model, bend.plan).objective,
        )


def test_default_optimize_remains_integrated() -> None:
    model = build_toy_field()
    opt = optimize_portfolio(model)
    assert opt.solver == "integrated"
