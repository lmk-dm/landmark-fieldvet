"""Price scenarios and CVaR."""

from __future__ import annotations

from landmark_fieldvet.examples import build_toy_field
from landmark_fieldvet.models import Plan, Prices, StartDecision
from landmark_fieldvet.scenarios import Scenario, evaluate_plan_scenarios


def test_price_scenarios_expected_and_cvar() -> None:
    model = build_toy_field()
    plan = Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0)))
    base = model.prices
    scenarios = (
        Scenario("base", 0.5, prices=base),
        Scenario(
            "low",
            0.25,
            prices=Prices(
                oil=base.oil * 0.7,
                gas=base.gas * 0.7,
                water_disposal=base.water_disposal,
                discount_rate_per_period=base.discount_rate_per_period,
            ),
        ),
        Scenario(
            "high",
            0.25,
            prices=Prices(
                oil=base.oil * 1.3,
                gas=base.gas * 1.3,
                water_disposal=base.water_disposal,
                discount_rate_per_period=base.discount_rate_per_period,
            ),
        ),
    )
    ev = evaluate_plan_scenarios(model, plan, scenarios, alpha=0.75)
    assert ev.expected_npv != 0.0
    # CVaR at 75% looks at worst 25% → the low scenario.
    low_obj = next(o.objective for o in ev.outcomes if o.scenario_id == "low")
    assert abs(ev.cvar - low_obj) < 1e-6
    assert ev.cvar <= ev.expected_npv + 1e-6
