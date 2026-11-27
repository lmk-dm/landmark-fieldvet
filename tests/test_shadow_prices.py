"""Capacity duals identify the binding compressor when pads compete."""

from __future__ import annotations

from landmark_field_network.examples import build_toy_field
from landmark_field_network.models import Plan, StartDecision
from landmark_field_network.network import debottleneck_candidates, solve_network


def test_binding_compressor_has_positive_shadow_price() -> None:
    model = build_toy_field()
    alone = solve_network(model, Plan(starts=(StartDecision("pad_a", 0),)))
    both = solve_network(
        model,
        Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
    )
    alone_shadow = sum(alone.shadow_price["comp_gas"])
    both_shadow = sum(both.shadow_price["comp_gas"])
    assert alone_shadow >= -1e-6
    assert both_shadow > alone_shadow + 1e-3


def test_debottleneck_candidate_from_shadow_prices() -> None:
    model = build_toy_field()
    both = solve_network(
        model,
        Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
    )
    # Cheap expansion should be suggested; expensive should not.
    cheap = debottleneck_candidates(both, expand_cost_per_unit={"comp_gas": 0.01})
    expensive = debottleneck_candidates(both, expand_cost_per_unit={"comp_gas": 1e12})
    assert any(arc == "comp_gas" for arc, _, _ in cheap)
    assert expensive == []
