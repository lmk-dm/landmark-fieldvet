"""Consumer path: hydraulic capacities → enumerated FieldVET plans → NPV."""

from __future__ import annotations

from landmark_fieldvet.examples.two_pad_tie_in import (
    BASE_SHARED_GAS_PER_PERIOD,
    PAD_GAS_PER_PERIOD,
    UPGRADE_SHARED_GAS_PER_PERIOD,
    build_two_pad_tie_in,
    compressor_capex_breakeven,
    enumerate_tie_in_plans,
    preferred_plan,
)
from landmark_fieldvet.models import Plan, StartDecision
from landmark_fieldvet.network import solve_network


def test_both_pads_curtail_without_upgrade() -> None:
    from landmark_fieldvet.models import Commodity

    model = build_two_pad_tie_in()
    both = solve_network(
        model,
        Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
    )
    # Forecast wants 2 * PAD_GAS; base shared capacity is lower.
    assert BASE_SHARED_GAS_PER_PERIOD < 2.0 * PAD_GAS_PER_PERIOD
    produced = sum(sum(both.produced[pad][Commodity.GAS]) for pad in both.produced)
    forecast = 2.0 * PAD_GAS_PER_PERIOD * model.n_periods
    assert produced < forecast - 1.0
    # Delivered gas should sit on the shared capacity ceiling.
    assert produced <= BASE_SHARED_GAS_PER_PERIOD * model.n_periods + 1e-3


def test_upgrade_clears_curtailment() -> None:
    from landmark_fieldvet.models import Commodity

    model = build_two_pad_tie_in()
    with_up = solve_network(
        model,
        Plan(
            starts=(
                StartDecision("pad_a", 0),
                StartDecision("pad_b", 0),
                StartDecision("comp_expand", 0),
            )
        ),
    )
    produced = sum(sum(with_up.produced[pad][Commodity.GAS]) for pad in with_up.produced)
    forecast = 2.0 * PAD_GAS_PER_PERIOD * model.n_periods
    assert produced == forecast
    assert UPGRADE_SHARED_GAS_PER_PERIOD >= 2.0 * PAD_GAS_PER_PERIOD


def test_enumeration_ranks_upgrade_above_both_alone() -> None:
    plans = {p.name: p for p in enumerate_tie_in_plans()}
    assert plans["both_pads_with_upgrade"].result.objective > plans["both_pads"].result.objective
    assert plans["both_pads_with_upgrade"].first_gas_period == 0
    pref = preferred_plan(list(plans.values()))
    assert pref.name == "both_pads_with_upgrade"


def test_single_pad_beats_curtailed_both_when_upgrade_too_expensive() -> None:
    # Extreme compressor capital: prefer a single pad over funding the upgrade.
    model = build_two_pad_tie_in(compressor_capital=1.0e12)
    plans = {p.name: p for p in enumerate_tie_in_plans(model)}
    assert plans["pad_a_only"].result.objective > plans["both_pads_with_upgrade"].result.objective


def test_capex_breakeven_is_positive() -> None:
    be = compressor_capex_breakeven()
    assert be > 0.0
    # At breakeven, both+upgrade ≈ both; slightly above, both wins.
    model_hi = build_two_pad_tie_in(compressor_capital=be + 100_000.0)
    both = solve_network(
        model_hi,
        Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
    )
    with_up = solve_network(
        model_hi,
        Plan(
            starts=(
                StartDecision("pad_a", 0),
                StartDecision("pad_b", 0),
                StartDecision("comp_expand", 0),
            )
        ),
    )
    assert both.objective >= with_up.objective
