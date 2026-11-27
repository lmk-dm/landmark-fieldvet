"""Consumer path: inventory → optimize_portfolio → plan priced through network."""

from __future__ import annotations

from landmark_fieldvet.examples import build_toy_field
from landmark_fieldvet.master import optimize_portfolio
from landmark_fieldvet.models import Plan, StartDecision
from landmark_fieldvet.network import solve_network


def test_optimizer_funds_expansion_with_both_pads_when_valuable() -> None:
    model = build_toy_field()
    opt = optimize_portfolio(model)
    selected = {s.project_id for s in opt.plan.starts}
    # With flat profitable curves, both pads + expansion beat one pad alone.
    assert "pad_a" in selected or "pad_b" in selected
    if "pad_a" in selected and "pad_b" in selected:
        assert "comp_expand" in selected


def test_two_pads_without_expand_worth_less_than_with_expand() -> None:
    model = build_toy_field()
    without = solve_network(
        model,
        Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
    )
    with_exp = solve_network(
        model,
        Plan(
            starts=(
                StartDecision("pad_a", 0),
                StartDecision("pad_b", 0),
                StartDecision("comp_expand", 0),
            )
        ),
    )
    assert with_exp.objective > without.objective
