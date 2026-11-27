"""Network flow subproblem for a fixed plan.

For each period: balance oil, gas, and water; respect arc capacities; apply one
throughput fraction per pad (preserves GOR / WOR). Duals on arc capacities and
on ``produced ≤ forecast`` feed Benders optimality cuts and debottleneck hints.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyomo.environ import (
    ConcreteModel,
    Constraint,
    NonNegativeReals,
    Objective,
    Param,
    RangeSet,
    Set,
    Suffix,
    Var,
    maximize,
    value,
)

from landmark_fieldvet.models import Commodity, FieldModel, NodeKind, Plan
from landmark_fieldvet.plan_effects import PlanEffects, apply_plan
from landmark_fieldvet.solvers import get_highs_solver


@dataclass(frozen=True)
class NetworkResult:
    objective: float
    """NPV of operating cash flow minus capital when include_capital=True."""

    operating_npv: float
    """Discounted revenue − disposal only (no capital)."""

    produced: dict[str, dict[Commodity, list[float]]]
    curtailed_fraction: dict[str, list[float]]
    flow: dict[str, list[float]]
    """arc_id -> period flow."""
    shadow_price: dict[str, list[float]]
    """arc_id -> period dual on capacity (d operating_obj / d capacity)."""
    forecast_shadow: dict[str, dict[Commodity, list[float]]]
    """pad -> commodity -> period dual on produced ≤ forecast."""
    capital: list[float]
    effects: PlanEffects


def _read_dual(m, result, con) -> float:
    try:
        return float(m.dual[con])
    except Exception:
        try:
            return float(result.solution_loader.get_duals()[con])
        except Exception:
            return 0.0


def solve_network(
    model: FieldModel,
    plan: Plan,
    *,
    tee: bool = False,
    include_capital: bool = True,
) -> NetworkResult:
    effects = apply_plan(model, plan)
    return solve_network_effects(
        model, effects, tee=tee, include_capital=include_capital
    )


def solve_network_effects(
    model: FieldModel,
    effects: PlanEffects,
    *,
    tee: bool = False,
    include_capital: bool = True,
) -> NetworkResult:
    n = model.n_periods
    prices = model.prices
    arcs = list(model.network.arcs)
    pad_nodes = sorted(
        {nd.id for nd in model.network.nodes if nd.kind is NodeKind.PAD}
        | set(effects.forecast.keys())
    )
    forecast = {
        pad: {
            c: list(effects.forecast[pad][c])
            if pad in effects.forecast
            else [0.0] * n
            for c in Commodity
        }
        for pad in pad_nodes
    }

    sales_nodes = {nd.id for nd in model.network.nodes if nd.kind is NodeKind.SALES}
    disposal_nodes = {nd.id for nd in model.network.nodes if nd.kind is NodeKind.DISPOSAL}
    node_ids = [nd.id for nd in model.network.nodes]

    m = ConcreteModel(name="fieldvet_network")
    m.T = RangeSet(0, n - 1)
    m.ARCS = Set(initialize=[a.id for a in arcs])
    m.PADS = Set(initialize=pad_nodes)
    m.NODES = Set(initialize=node_ids)
    m.COMMODITIES = Set(initialize=[c.value for c in Commodity])

    m.capacity = Param(
        m.ARCS,
        m.T,
        initialize={(a.id, t): effects.capacity[a.id][t] for a in arcs for t in range(n)},
        mutable=False,
    )
    m.forecast = Param(
        m.PADS,
        m.COMMODITIES,
        m.T,
        initialize={
            (pad, c.value, t): forecast[pad][c][t]
            for pad in pad_nodes
            for c in Commodity
            for t in range(n)
        },
        mutable=False,
    )

    m.flow = Var(m.ARCS, m.T, domain=NonNegativeReals)
    m.produced = Var(m.PADS, m.COMMODITIES, m.T, domain=NonNegativeReals)
    m.sink = Var(m.NODES, m.COMMODITIES, m.T, domain=NonNegativeReals)

    def capacity_rule(mm, a, t):
        return mm.flow[a, t] <= mm.capacity[a, t]

    m.capacity_con = Constraint(m.ARCS, m.T, rule=capacity_rule)

    def prod_limit_rule(mm, pad, commodity, t):
        return mm.produced[pad, commodity, t] <= mm.forecast[pad, commodity, t]

    m.prod_limit = Constraint(m.PADS, m.COMMODITIES, m.T, rule=prod_limit_rule)

    # Shared throughput fraction across phases: produced[c] * F[oil] = produced[oil] * F[c]
    # when oil forecast is the reference; if oil forecast is 0, use gas as reference.
    def coupling_rule(mm, pad, commodity, t):
        if commodity == Commodity.OIL.value:
            return Constraint.Skip
        f_oil = forecast[pad][Commodity.OIL][t]
        f_c = forecast[pad][Commodity(commodity)][t]
        if f_oil > 1e-12:
            return (
                mm.produced[pad, commodity, t] * f_oil
                == mm.produced[pad, Commodity.OIL.value, t] * f_c
            )
        f_gas = forecast[pad][Commodity.GAS][t]
        if commodity == Commodity.GAS.value or f_gas <= 1e-12:
            return Constraint.Skip
        return (
            mm.produced[pad, commodity, t] * f_gas
            == mm.produced[pad, Commodity.GAS.value, t] * f_c
        )

    m.coupling = Constraint(m.PADS, m.COMMODITIES, m.T, rule=coupling_rule)

    def balance_rule(mm, node, commodity, t):
        inflow = sum(
            mm.flow[a.id, t] for a in arcs if a.target == node and a.commodity.value == commodity
        )
        outflow = sum(
            mm.flow[a.id, t] for a in arcs if a.source == node and a.commodity.value == commodity
        )
        supply = mm.produced[node, commodity, t] if node in pad_nodes else 0.0
        return inflow + supply == outflow + mm.sink[node, commodity, t]

    m.balance = Constraint(m.NODES, m.COMMODITIES, m.T, rule=balance_rule)

    def sink_allowed_rule(mm, node, commodity, t):
        if commodity == Commodity.WATER.value:
            allowed = node in disposal_nodes
        else:
            allowed = node in sales_nodes
        if allowed:
            return Constraint.Skip
        return mm.sink[node, commodity, t] == 0.0

    m.sink_allowed = Constraint(m.NODES, m.COMMODITIES, m.T, rule=sink_allowed_rule)

    def operating_rule(mm):
        total = 0.0
        for t in mm.T:
            df = (1.0 + prices.discount_rate_per_period) ** (-t)
            oil = sum(mm.sink[node, Commodity.OIL.value, t] for node in sales_nodes)
            gas = sum(mm.sink[node, Commodity.GAS.value, t] for node in sales_nodes)
            water = sum(mm.sink[node, Commodity.WATER.value, t] for node in disposal_nodes)
            revenue = prices.oil * oil + prices.gas * gas - prices.water_disposal * water
            total += df * revenue
        return total

    m.operating = Objective(rule=operating_rule, sense=maximize)
    m.dual = Suffix(direction=Suffix.IMPORT)

    solver = get_highs_solver(tee=tee)
    if hasattr(solver, "highs_options"):
        solver.highs_options = {"parallel": "off"}
    result = solver.solve(m, tee=tee)
    from pyomo.opt import TerminationCondition

    tc = result.solver.termination_condition
    if tc not in {
        TerminationCondition.optimal,
        TerminationCondition.feasible,
    }:
        raise RuntimeError(f"network subproblem did not solve optimally: {tc}")

    operating_npv = float(value(m.operating))
    capital_npv = 0.0
    for t in range(n):
        df = (1.0 + prices.discount_rate_per_period) ** (-t)
        capital_npv += df * effects.capital[t]
    objective = operating_npv - capital_npv if include_capital else operating_npv

    produced: dict[str, dict[Commodity, list[float]]] = {
        pad: {c: [0.0] * n for c in Commodity} for pad in pad_nodes
    }
    curtail_out: dict[str, list[float]] = {pad: [0.0] * n for pad in pad_nodes}
    flow_out: dict[str, list[float]] = {a.id: [0.0] * n for a in arcs}
    shadow: dict[str, list[float]] = {a.id: [0.0] * n for a in arcs}
    forecast_shadow: dict[str, dict[Commodity, list[float]]] = {
        pad: {c: [0.0] * n for c in Commodity} for pad in pad_nodes
    }

    for pad in pad_nodes:
        for t in range(n):
            f_oil = forecast[pad][Commodity.OIL][t]
            p_oil = float(value(m.produced[pad, Commodity.OIL.value, t]))
            if f_oil > 1e-12:
                curtail_out[pad][t] = 1.0 - p_oil / f_oil
            else:
                f_gas = forecast[pad][Commodity.GAS][t]
                p_gas = float(value(m.produced[pad, Commodity.GAS.value, t]))
                curtail_out[pad][t] = (1.0 - p_gas / f_gas) if f_gas > 1e-12 else 0.0
            for c in Commodity:
                produced[pad][c][t] = float(value(m.produced[pad, c.value, t]))
                # Maximize: Pyomo dual of ≤ is often ≤ 0; report sensitivity dZ/dF ≥ 0.
                raw = _read_dual(m, result, m.prod_limit[pad, c.value, t])
                forecast_shadow[pad][c][t] = abs(raw)

    for a in arcs:
        for t in range(n):
            flow_out[a.id][t] = float(value(m.flow[a.id, t]))
            raw = _read_dual(m, result, m.capacity_con[a.id, t])
            shadow[a.id][t] = abs(raw)

    return NetworkResult(
        objective=objective,
        operating_npv=operating_npv,
        produced=produced,
        curtailed_fraction=curtail_out,
        flow=flow_out,
        shadow_price=shadow,
        forecast_shadow=forecast_shadow,
        capital=list(effects.capital),
        effects=effects,
    )


def debottleneck_candidates(
    result: NetworkResult,
    *,
    expand_cost_per_unit: dict[str, float],
) -> list[tuple[str, float, float]]:
    """Arcs where Σ_t shadow_price exceeds expansion cost per unit capacity."""
    out: list[tuple[str, float, float]] = []
    for arc_id, series in result.shadow_price.items():
        total = sum(series)
        cost = expand_cost_per_unit.get(arc_id)
        if cost is None:
            continue
        if total > cost + 1e-9:
            out.append((arc_id, total, cost))
    return out
