"""Consumer path: fixed plan → network subproblem → curtailment.

Two pads on a compressor sized for one must curtail. One pad alone must not.
"""

from __future__ import annotations

from landmark_field_network.examples import build_toy_field
from landmark_field_network.models import Commodity, Plan, StartDecision
from landmark_field_network.network import solve_network


def test_single_pad_flows_uncurtailed() -> None:
    model = build_toy_field()
    result = solve_network(model, Plan(starts=(StartDecision("pad_a", 0),)))
    assert all(c < 1e-8 for c in result.curtailed_fraction["pad_a"])
    assert result.produced["pad_a"][Commodity.GAS][0] == 100.0


def test_two_pads_share_compressor_and_curtail() -> None:
    model = build_toy_field()
    result = solve_network(
        model,
        Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
    )
    # Combined peak gas 200 into capacity 100 → total delivered gas = 100 / period.
    total_gas = sum(
        result.produced["pad_a"][Commodity.GAS][t] + result.produced["pad_b"][Commodity.GAS][t]
        for t in range(model.n_periods)
    )
    assert abs(total_gas - 100.0 * model.n_periods) < 1e-4
    assert max(result.curtailed_fraction["pad_a"] + result.curtailed_fraction["pad_b"]) > 0.4


def test_expansion_removes_curtailment() -> None:
    model = build_toy_field()
    result = solve_network(
        model,
        Plan(
            starts=(
                StartDecision("pad_a", 0),
                StartDecision("pad_b", 0),
                StartDecision("comp_expand", 0),
            )
        ),
    )
    assert all(c < 1e-8 for c in result.curtailed_fraction["pad_a"])
    assert all(c < 1e-8 for c in result.curtailed_fraction["pad_b"])
