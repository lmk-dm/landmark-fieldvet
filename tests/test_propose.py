"""Auto-generate facility projects from shadow prices."""

from __future__ import annotations

from landmark_field_network.examples import build_toy_field
from landmark_field_network.models import Plan, StartDecision
from landmark_field_network.network import solve_network
from landmark_field_network.propose import propose_facility_projects, with_proposed_facilities


def test_propose_expansion_when_compressor_binds() -> None:
    model = build_toy_field()
    # Both pads, no expand → compressor binds.
    result = solve_network(
        model,
        Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
    )
    proposed = propose_facility_projects(
        model,
        result,
        expand_cost_per_unit={"comp_gas": 1.0},
        capacity_add=100.0,
        capital=1_000.0,
    )
    assert any(p.id == "auto_expand_comp_gas" for p in proposed)
    assert proposed[0].capacity_adds["comp_gas"] == 100.0

    enriched = with_proposed_facilities(
        model,
        result,
        expand_cost_per_unit={"comp_gas": 1.0},
        capacity_add=100.0,
        capital=1_000.0,
    )
    assert len(enriched.projects) == len(model.projects) + 1
