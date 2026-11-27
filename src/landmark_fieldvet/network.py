"""Network flow subproblem for a fixed plan.

For each period: balance oil, gas, and water; respect arc capacities; apply one
curtailment fraction per pad (preserves GOR / WOR, keeps the coupling linear).
Duals on arc capacities are the capacity shadow prices that feed Benders cuts
and debottlenecking candidates.
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
    """Operating NPV (revenue − disposal − capital), discounted."""

    produced: dict[str, dict[Commodity, list[float]]]
    curtailed_fraction: dict[str, list[float]]
    flow: dict[str, list[float]]
    """arc_id -> period flow."""
    shadow_price: dict[str, list[float]]
    """arc_id -> period dual on capacity (undiscounted primal units × price basis)."""
    capital: list[float]
    effects: PlanEffects


def solve_network(
    model: FieldModel,
    plan: Plan,
    *,
    tee: bool = False,
) -> NetworkResult:
    effects = apply_plan(model, plan)
    return solve_network_effects(model, effects, tee=tee)


def solve_network_effects(
    model: FieldModel,
    effects: PlanEffects,
    *,
    tee: bool = False,
) -> NetworkResult:
    n = model.n_periods
    prices = model.prices
    arcs = list(model.network.arcs)
    pads = sorted(effects.forecast.keys())
    sales_nodes = {nd.id for nd in model.network.nodes if nd.kind is NodeKind.SALES}
    disposal_nodes = {nd.id for nd in model.network.nodes if nd.kind is NodeKind.DISPOSAL}
    node_ids = [nd.id for nd in model.network.nodes]

    m = ConcreteModel(name="fieldvet_network")
    m.T = RangeSet(0, n - 1)
    m.ARCS = Set(initialize=[a.id for a in arcs])
    m.PADS = Set(initialize=pads)
    m.NODES = Set(initialize=node_ids)
    m.COMMODITIES = Set(initialize=[c.value for c in Commodity])

    arc_map = {a.id: a for a in arcs}
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
            (pad, c.value, t): effects.forecast[pad][c][t]
            for pad in pads
            for c in Commodity
            for t in range(n)
        },
        mutable=False,
    )

    m.flow = Var(m.ARCS, m.T, domain=NonNegativeReals)
    m.curtail = Var(m.PADS, m.T, domain=NonNegativeReals, bounds=(0.0, 1.0))
    # Sales / disposal sinks absorb unbalanced mass at those nodes.
    m.sink = Var(m.NODES, m.COMMODITIES, m.T, domain=NonNegativeReals)

    def capacity_rule(mm, a, t):
        return mm.flow[a, t] <= mm.capacity[a, t]

    m.capacity_con = Constraint(m.ARCS, m.T, rule=capacity_rule)

    def balance_rule(mm, node, commodity, t):
        inflow = sum(
            mm.flow[a.id, t] for a in arcs if a.target == node and a.commodity.value == commodity
        )
        outflow = sum(
            mm.flow[a.id, t] for a in arcs if a.source == node and a.commodity.value == commodity
        )
        supply = 0.0
        if node in pads:
            # produced = forecast * (1 - curtail)
            supply = mm.forecast[node, commodity, t] * (1 - mm.curtail[node, t])
        # Only sales (oil/gas) and disposal (water) may sink commodity.
        sink = mm.sink[node, commodity, t]
        if commodity == Commodity.WATER.value:
            if node not in disposal_nodes and node not in pads:
                # intermediate nodes: sink forced to 0 via constraint below
                pass
        return inflow + supply == outflow + sink

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

    def objective_rule(mm):
        total = 0.0
        for t in mm.T:
            df = (1.0 + prices.discount_rate_per_period) ** (-t)
            oil = sum(
                mm.sink[node, Commodity.OIL.value, t] for node in sales_nodes
            )
            gas = sum(
                mm.sink[node, Commodity.GAS.value, t] for node in sales_nodes
            )
            water = sum(
                mm.sink[node, Commodity.WATER.value, t] for node in disposal_nodes
            )
            revenue = prices.oil * oil + prices.gas * gas - prices.water_disposal * water
            total += df * revenue
            total -= df * effects.capital[t]
        return total

    m.obj = Objective(rule=objective_rule, sense=maximize)
    m.dual = Suffix(direction=Suffix.IMPORT)

    solver = get_highs_solver(tee=tee)
    # APPSI HiGHS loads duals when solver_options request them.
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

    produced: dict[str, dict[Commodity, list[float]]] = {
        pad: {c: [0.0] * n for c in Commodity} for pad in pads
    }
    curtail_out: dict[str, list[float]] = {pad: [0.0] * n for pad in pads}
    flow_out: dict[str, list[float]] = {a.id: [0.0] * n for a in arcs}
    shadow: dict[str, list[float]] = {a.id: [0.0] * n for a in arcs}

    for pad in pads:
        for t in range(n):
            frac = float(value(m.curtail[pad, t]))
            curtail_out[pad][t] = frac
            for c in Commodity:
                produced[pad][c][t] = effects.forecast[pad][c][t] * (1.0 - frac)

    for a in arcs:
        for t in range(n):
            flow_out[a.id][t] = float(value(m.flow[a.id, t]))
            dual = 0.0
            try:
                dual = float(m.dual[m.capacity_con[a.id, t]])
            except Exception:
                # APPSI solution loader
                try:
                    loader = result.solution_loader
                    dual = float(loader.get_duals()[m.capacity_con[a.id, t]])
                except Exception:
                    dual = 0.0
            shadow[a.id][t] = dual

    return NetworkResult(
        objective=float(value(m.obj)),
        produced=produced,
        curtailed_fraction=curtail_out,
        flow=flow_out,
        shadow_price=shadow,
        capital=list(effects.capital),
        effects=effects,
    )


def debottleneck_candidates(
    result: NetworkResult,
    *,
    expand_cost_per_unit: dict[str, float],
) -> list[tuple[str, float, float]]:
    """Arcs where Σ_t shadow_price exceeds expansion cost per unit capacity.

    Returns (arc_id, total_shadow, cost) for candidates worth generating.
    """
    out: list[tuple[str, float, float]] = []
    for arc_id, series in result.shadow_price.items():
        total = sum(series)
        cost = expand_cost_per_unit.get(arc_id)
        if cost is None:
            continue
        if total > cost + 1e-9:
            out.append((arc_id, total, cost))
    return out
