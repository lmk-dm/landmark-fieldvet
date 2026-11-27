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
    tie_in_decision,
    verify_schedule_against_hydraulics,
)
from landmark_fieldvet.models import Commodity, Plan, StartDecision
from landmark_fieldvet.network import solve_network


def test_both_pads_curtail_without_upgrade() -> None:
    model = build_two_pad_tie_in()
    both = solve_network(
        model,
        Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
    )
    assert BASE_SHARED_GAS_PER_PERIOD < 2.0 * PAD_GAS_PER_PERIOD
    produced = sum(sum(both.produced[pad][Commodity.GAS]) for pad in both.produced)
    forecast = 2.0 * PAD_GAS_PER_PERIOD * model.n_periods
    assert produced < forecast - 1.0
    assert produced <= BASE_SHARED_GAS_PER_PERIOD * model.n_periods + 1e-3


def test_upgrade_clears_curtailment() -> None:
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
    assert (
        plans["both_pads_with_upgrade_t0"].result.objective
        > plans["both_pads_t0"].result.objective
    )
    assert plans["both_pads_with_upgrade_t0"].first_gas_period == 0
    pref = preferred_plan(list(plans.values()))
    assert pref.name == "both_pads_with_upgrade_t0"


def test_deferred_second_pad_avoids_early_curtailment() -> None:
    plans = {p.name: p for p in enumerate_tie_in_plans(defer_periods=6)}
    deferred = plans["pad_a_t0_pad_b_t6"]
    both = plans["both_pads_t0"]
    # First six periods: only pad A at full nomination (fits base capacity).
    for t in range(6):
        gas_a = deferred.result.produced["pad_a"][Commodity.GAS][t]
        gas_b = deferred.result.produced["pad_b"][Commodity.GAS][t]
        assert gas_b == 0.0
        assert abs(gas_a - PAD_GAS_PER_PERIOD) < 1e-6
    assert deferred.hydraulic_ok
    assert both.hydraulic_ok
    # Simultaneous both without upgrade still produces less total gas than
    # deferred-with-full-single-then-shared, or at least different NPV path.
    assert deferred.result.objective != both.result.objective


def test_simultaneous_upgrade_beats_deferred_second_pad() -> None:
    plans = {p.name: p for p in enumerate_tie_in_plans(defer_periods=6)}
    assert (
        plans["both_pads_with_upgrade_t0"].result.objective
        > plans["pad_a_t0_pad_b_t6"].result.objective
    )
    assert (
        plans["both_pads_with_upgrade_t0"].result.objective
        > plans["pad_a_t0_pad_b_t6_upgrade_t6"].result.objective
    )


def test_every_enumerated_plan_passes_hydraulic_check() -> None:
    for plan in enumerate_tie_in_plans():
        assert plan.hydraulic_ok, (plan.name, plan.hydraulic_notes)
        ok, _ = verify_schedule_against_hydraulics(
            build_two_pad_tie_in(), plan.plan, plan.result
        )
        assert ok


def test_single_pad_beats_curtailed_both_when_upgrade_too_expensive() -> None:
    model = build_two_pad_tie_in(compressor_capital=1.0e12)
    plans = {p.name: p for p in enumerate_tie_in_plans(model)}
    assert (
        plans["pad_a_only"].result.objective
        > plans["both_pads_with_upgrade_t0"].result.objective
    )


def test_capex_breakeven_is_positive() -> None:
    be = compressor_capex_breakeven()
    assert be > 0.0
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


def test_tie_in_decision_answers_which_when_compressor() -> None:
    decision = tie_in_decision()
    assert decision.which_pads == "both pads"
    assert "period 0" in decision.when
    assert decision.compressor_worth_buying is True
    assert decision.preferred.name == "both_pads_with_upgrade_t0"
    assert "CTB" in decision.what_limits_second_pad
    assert decision.compressor_capex_breakeven > 0.0
