"""20-pad / 5-facility area: solvers agree on NPV; economics handoff preserves the plan.

Integrated MILP certifies the optimum at this size (~2.5s). Benders finds the same
NPV; formal dual-gap closure is proven through 16 pads and remains open at 20.
"""

from __future__ import annotations

from landmark_fieldvet.attribution import attribute
from landmark_fieldvet.examples import build_operator_scale
from landmark_fieldvet.examples.operator_scale import N_FACILITIES, N_PADS
from landmark_fieldvet.export import economics_project_list
from landmark_fieldvet.master import optimize_portfolio
from landmark_fieldvet.network import solve_network


def test_operator_scale_inventory_shape() -> None:
    model = build_operator_scale()
    assert sum(1 for p in model.projects if p.kind.value == "development") == N_PADS
    assert (
        sum(1 for p in model.projects if p.kind.value in {"facility", "commercial"})
        == N_FACILITIES
    )
    assert model.n_periods == 12
    assert model.fix_to_earliest_start is True
    assert model.allowed_starts() == (0, 3, 6, 9)


def test_benders_converges_through_16_pads() -> None:
    model = build_operator_scale(n_pads=16)
    opt = optimize_portfolio(
        model,
        method="benders",
        abs_tol=50.0,
        rel_tol=1e-3,
        time_limit_sec=60.0,
        max_iterations=40,
    )
    assert opt.stats is not None
    assert opt.stats.converged, opt.stats


def test_operator_scale_20_pad_solvers_agree_on_npv() -> None:
    model = build_operator_scale(n_pads=20)
    integ = optimize_portfolio(model, method="integrated")
    bend = optimize_portfolio(
        model,
        method="benders",
        abs_tol=50.0,
        rel_tol=1e-3,
        time_limit_sec=60.0,
        max_iterations=40,
    )
    assert abs(integ.objective - bend.objective) <= 50.0
    assert abs(integ.objective - solve_network(model, integ.plan).objective) < 1e-4
    selected = {s.project_id for s in integ.plan.starts}
    assert any(pid.startswith("pad_") for pid in selected)
    assert selected & {
        "comp_expand",
        "north_oil_loop",
        "south_oil_loop",
        "swd_expand",
        "firm_gas_transport",
    }


def test_operator_scale_attribution_and_economics_handoff(tmp_path) -> None:
    model = build_operator_scale(n_pads=20)
    opt = optimize_portfolio(model, method="integrated")
    report = attribute(
        model,
        opt.plan,
        portfolio_result=opt.network,
        include_interaction=False,
        include_shapley=False,
    )
    assert report.portfolio_npv == opt.objective
    assert report.standalone
    assert report.marginal

    handoff = economics_project_list(
        model, opt.plan, opt.network, case_id="operator_scale_v1"
    )
    assert handoff.n_periods == 12
    assert len(handoff.projects) == sum(
        1 for s in opt.plan.starts if s.project_id.startswith("pad_")
    )
    assert handoff.portfolio_npv_linear == opt.objective
    path = handoff.write_json(tmp_path / "operator_scale_handoff.json")
    assert path.exists()
    for proj in handoff.projects:
        assert len(proj.oil_bbl) == 12
        assert sum(proj.oil_bbl) >= 0.0
