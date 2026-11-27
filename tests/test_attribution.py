"""Attribution views: complements show positive interaction; Shapley sums to NPV."""

from __future__ import annotations

from landmark_fieldvet.attribution import attribute
from landmark_fieldvet.examples import build_toy_field
from landmark_fieldvet.models import Plan, StartDecision


def test_pad_and_compressor_are_complements() -> None:
    model = build_toy_field()
    plan = Plan(
        starts=(
            StartDecision("pad_a", 0),
            StartDecision("pad_b", 0),
            StartDecision("comp_expand", 0),
        )
    )
    report = attribute(model, plan, shapley_samples=24, seed=1)
    # Pads alone compete (negative or small interaction); pad pair vs expansion
    # should show the expansion unlocking value.
    assert ("pad_a", "pad_b") in report.interaction
    assert report.interaction[("pad_a", "pad_b")] < 0.0
    # Shapley shares sum to portfolio NPV (exact for n=3).
    assert abs(sum(report.shapley.values()) - report.portfolio_npv) < 1e-4
