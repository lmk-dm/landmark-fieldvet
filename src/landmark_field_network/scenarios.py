"""Price / type-curve scenarios and CVaR over a fixed plan.

For price-only scenarios the network solve is reused (production fixed) and cash
flows are revalued. Type-curve overrides re-solve the network subproblem.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

from landmark_field_network.models import Commodity, FieldModel, Plan, Prices, Project, TypeCurve
from landmark_field_network.network import NetworkResult, solve_network
from landmark_field_network.plan_effects import apply_plan


@dataclass(frozen=True)
class Scenario:
    id: str
    probability: float
    prices: Prices | None = None
    """If set, overrides FieldModel.prices for valuation / re-solve."""
    type_curves: Mapping[str, TypeCurve] = field(default_factory=dict)
    """project_id → override type curve (development projects only)."""

    def __post_init__(self) -> None:
        if self.probability < 0.0:
            raise ValueError("probability must be non-negative")


@dataclass(frozen=True)
class ScenarioOutcome:
    scenario_id: str
    probability: float
    objective: float
    network: NetworkResult


@dataclass(frozen=True)
class ScenarioEvaluation:
    outcomes: tuple[ScenarioOutcome, ...]
    expected_npv: float
    cvar: float
    """Conditional value at risk at ``alpha`` (mean of worst tail)."""
    alpha: float
    var: float
    """Value-at-risk threshold used when filling the CVaR tail."""

    def to_dict(self) -> dict:
        return {
            "expected_npv": self.expected_npv,
            "cvar": self.cvar,
            "var": self.var,
            "alpha": self.alpha,
            "outcomes": [
                {
                    "scenario_id": o.scenario_id,
                    "probability": o.probability,
                    "objective": o.objective,
                }
                for o in self.outcomes
            ],
        }


def _model_for_scenario(model: FieldModel, scenario: Scenario) -> FieldModel:
    prices = scenario.prices or model.prices
    if not scenario.type_curves:
        return replace(model, prices=prices)
    projects: list[Project] = []
    for p in model.projects:
        tc = scenario.type_curves.get(p.id)
        projects.append(p if tc is None else replace(p, type_curve=tc))
    return replace(model, prices=prices, projects=tuple(projects))


def _revalue_fixed_production(
    model: FieldModel,
    plan: Plan,
    base: NetworkResult,
    prices: Prices,
) -> float:
    """Reprice a solved production path under alternate flat prices."""
    effects = apply_plan(model, plan)
    n = model.n_periods
    operating = 0.0
    for t in range(n):
        df = (1.0 + prices.discount_rate_per_period) ** (-t)
        oil = sum(base.produced[pad][Commodity.OIL][t] for pad in base.produced)
        gas = sum(base.produced[pad][Commodity.GAS][t] for pad in base.produced)
        water = sum(base.produced[pad][Commodity.WATER][t] for pad in base.produced)
        revenue = prices.oil * oil + prices.gas * gas - prices.water_disposal * water
        operating += df * revenue
    capital_npv = 0.0
    for t in range(n):
        df = (1.0 + prices.discount_rate_per_period) ** (-t)
        capital_npv += df * effects.capital[t]
    return operating - capital_npv


def evaluate_plan_scenarios(
    model: FieldModel,
    plan: Plan,
    scenarios: Sequence[Scenario],
    *,
    alpha: float = 0.95,
) -> ScenarioEvaluation:
    """Evaluate a fixed plan under scenarios; report E[NPV] and CVaR."""
    if not scenarios:
        raise ValueError("at least one scenario is required")
    prob_sum = sum(s.probability for s in scenarios)
    if abs(prob_sum - 1.0) > 1e-6:
        raise ValueError(f"scenario probabilities must sum to 1, got {prob_sum}")
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must be in (0, 1)")

    outcomes: list[ScenarioOutcome] = []
    base_cache: NetworkResult | None = None

    for scenario in scenarios:
        needs_resolve = bool(scenario.type_curves)
        scen_model = _model_for_scenario(model, scenario)
        if needs_resolve:
            network = solve_network(scen_model, plan)
            objective = network.objective
        else:
            if base_cache is None:
                base_cache = solve_network(model, plan)
            prices = scenario.prices or model.prices
            if prices == model.prices:
                network = base_cache
                objective = base_cache.objective
            else:
                network = base_cache
                objective = _revalue_fixed_production(model, plan, base_cache, prices)
        outcomes.append(
            ScenarioOutcome(
                scenario_id=scenario.id,
                probability=scenario.probability,
                objective=objective,
                network=network,
            )
        )

    expected = sum(o.probability * o.objective for o in outcomes)
    ordered = sorted(outcomes, key=lambda o: o.objective)
    tail_mass = 1.0 - alpha
    remaining = tail_mass
    cvar_num = 0.0
    var = ordered[0].objective
    for o in ordered:
        if remaining <= 1e-15:
            break
        take = min(o.probability, remaining)
        cvar_num += take * o.objective
        var = o.objective
        remaining -= take
    cvar = cvar_num / tail_mass if tail_mass > 0 else expected

    return ScenarioEvaluation(
        outcomes=tuple(outcomes),
        expected_npv=expected,
        cvar=cvar,
        alpha=alpha,
        var=var,
    )
