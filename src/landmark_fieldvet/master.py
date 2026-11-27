"""Selection-and-timing master.

Default solver is the integrated MILP (reference for cases it can certify).
``method="benders"`` keeps binaries in a master problem and reuses the
fixed-plan network LP as the operating subproblem.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

from pyomo.environ import (
    Binary,
    ConcreteModel,
    Constraint,
    NonNegativeReals,
    Objective,
    RangeSet,
    Set,
    Var,
    maximize,
    value,
)

from landmark_fieldvet.models import (
    Commodity,
    FieldModel,
    NodeKind,
    Plan,
    ProjectKind,
    StartDecision,
)
from landmark_fieldvet.network import NetworkResult, solve_network
from landmark_fieldvet.solvers import get_highs_solver

SolverMethod = Literal["integrated", "benders"]


@dataclass(frozen=True)
class OptimizeResult:
    plan: Plan
    network: NetworkResult
    objective: float
    solver: str = "integrated"
    runtime_sec: float = 0.0
    stats: Any | None = None


def optimize_portfolio(
    model: FieldModel,
    *,
    method: SolverMethod = "integrated",
    tee: bool = False,
    abs_tol: float = 1.0,
    rel_tol: float = 1e-4,
    time_limit_sec: float = 120.0,
    max_iterations: int = 80,
) -> OptimizeResult:
    """Choose starts to maximize network-priced NPV under budgets and logic."""
    if method == "benders":
        from landmark_fieldvet.benders import optimize_benders

        result = optimize_benders(
            model,
            tee=tee,
            abs_tol=abs_tol,
            rel_tol=rel_tol,
            time_limit_sec=time_limit_sec,
            max_iterations=max_iterations,
        )
        return OptimizeResult(
            plan=result.plan,
            network=result.network,
            objective=result.objective,
            solver="benders",
            runtime_sec=result.stats.runtime_sec,
            stats=result.stats,
        )
    if method != "integrated":
        raise ValueError(f"unknown solver method: {method!r}")
    return _optimize_integrated(model, tee=tee)


def _optimize_integrated(model: FieldModel, *, tee: bool = False) -> OptimizeResult:
    started = time.perf_counter()
    n = model.n_periods
    prices = model.prices
    projects = list(model.projects)
    arcs = list(model.network.arcs)
    nodes = list(model.network.nodes)
    pads = sorted(
        {
            p.pad_node
            for p in projects
            if p.kind is ProjectKind.DEVELOPMENT and p.pad_node is not None
        }
    )
    sales = {nd.id for nd in nodes if nd.kind is NodeKind.SALES}
    disposal = {nd.id for nd in nodes if nd.kind is NodeKind.DISPOSAL}
    devel = [p for p in projects if p.kind is ProjectKind.DEVELOPMENT]

    m = ConcreteModel(name="fieldvet_master")
    m.T = RangeSet(0, n - 1)
    m.J = Set(initialize=[p.id for p in projects])
    m.JD = Set(initialize=[p.id for p in devel])
    m.ARCS = Set(initialize=[a.id for a in arcs])
    m.PADS = Set(initialize=pads)
    m.NODES = Set(initialize=[nd.id for nd in nodes])
    m.COMMODITIES = Set(initialize=[c.value for c in Commodity])

    m.x = Var(m.J, m.T, domain=Binary)
    # z[j,τ,t]: fraction of start (j,τ) that is produced in period t (≤ x[j,τ]).
    m.z = Var(m.JD, m.T, m.T, domain=NonNegativeReals, bounds=(0.0, 1.0))
    m.flow = Var(m.ARCS, m.T, domain=NonNegativeReals)
    m.sink = Var(m.NODES, m.COMMODITIES, m.T, domain=NonNegativeReals)
    m.cap = Var(m.ARCS, m.T, domain=NonNegativeReals)
    m.capital = Var(m.T, domain=NonNegativeReals)

    def one_start_rule(mm, j):
        return sum(mm.x[j, t] for t in mm.T) <= 1

    m.one_start = Constraint(m.J, rule=one_start_rule)

    def earliest_rule(mm, j, t):
        proj = model.project_by_id()[j]
        if t < proj.earliest_start:
            return mm.x[j, t] == 0
        return Constraint.Skip

    m.earliest = Constraint(m.J, m.T, rule=earliest_rule)

    groups: dict[str, list[str]] = {}
    for p in projects:
        if p.group:
            groups.setdefault(p.group, []).append(p.id)

    if groups:
        m.GROUPS = Set(initialize=list(groups.keys()))

        def group_rule(mm, g):
            members = groups[g]
            return sum(mm.x[j, t] for j in members for t in mm.T) <= 1

        m.group_excl = Constraint(m.GROUPS, rule=group_rule)

    extra = [(p.id, r, t) for p in projects for r in p.requires for t in range(n)]
    if extra:
        m.REQ = Set(initialize=extra, dimen=3)

        def requires_pair_rule(mm, j, r, t):
            return sum(mm.x[r, tau] for tau in mm.T if tau <= t) >= mm.x[j, t]

        m.requires_pair = Constraint(m.REQ, rule=requires_pair_rule)

    def z_bound_rule(mm, j, tau, t):
        return mm.z[j, tau, t] <= mm.x[j, tau]

    m.z_bound = Constraint(m.JD, m.T, m.T, rule=z_bound_rule)

    def z_before_online_rule(mm, j, tau, t):
        lead = model.project_by_id()[j].lead_time
        if t < tau + lead:
            return mm.z[j, tau, t] == 0
        return Constraint.Skip

    m.z_before = Constraint(m.JD, m.T, m.T, rule=z_before_online_rule)

    base = {a.id: a.base_capacity for a in arcs}

    def capacity_def_rule(mm, a, t):
        add = 0.0
        for p in projects:
            if a not in p.capacity_adds:
                continue
            for tau in range(n):
                if tau + p.lead_time <= t:
                    add += p.capacity_adds[a] * mm.x[p.id, tau]
        return mm.cap[a, t] == base[a] + add

    m.capacity_def = Constraint(m.ARCS, m.T, rule=capacity_def_rule)

    def capacity_limit_rule(mm, a, t):
        return mm.flow[a, t] <= mm.cap[a, t]

    m.capacity_limit = Constraint(m.ARCS, m.T, rule=capacity_limit_rule)

    def capital_def_rule(mm, t):
        total = 0.0
        for p in projects:
            for tau in range(n):
                age = t - tau
                spend = p.capital[age] if 0 <= age < len(p.capital) else 0.0
                total += spend * mm.x[p.id, tau]
        return mm.capital[t] == total

    m.capital_def = Constraint(m.T, rule=capital_def_rule)

    if model.capital_budget is not None:
        budgets = list(model.capital_budget)
        if len(budgets) != n:
            raise ValueError("capital_budget length must equal n_periods")

        def budget_rule(mm, t):
            return mm.capital[t] <= budgets[t]

        m.budget = Constraint(m.T, rule=budget_rule)

    def produced(pad: str, commodity: str, t: int):
        total = 0.0
        c = Commodity(commodity)
        for p in devel:
            if p.pad_node != pad or p.type_curve is None:
                continue
            for tau in range(n):
                online_from = tau + p.lead_time
                age = t - online_from
                rate = p.type_curve.at(age, c) if age >= 0 else 0.0
                total += rate * m.z[p.id, tau, t]
        return total

    def balance_rule(mm, node, commodity, t):
        inflow = sum(
            mm.flow[a.id, t]
            for a in arcs
            if a.target == node and a.commodity.value == commodity
        )
        outflow = sum(
            mm.flow[a.id, t]
            for a in arcs
            if a.source == node and a.commodity.value == commodity
        )
        supply = produced(node, commodity, t) if node in pads else 0.0
        return inflow + supply == outflow + mm.sink[node, commodity, t]

    m.balance = Constraint(m.NODES, m.COMMODITIES, m.T, rule=balance_rule)

    def sink_allowed_rule(mm, node, commodity, t):
        if commodity == Commodity.WATER.value:
            allowed = node in disposal
        else:
            allowed = node in sales
        if allowed:
            return Constraint.Skip
        return mm.sink[node, commodity, t] == 0.0

    m.sink_allowed = Constraint(m.NODES, m.COMMODITIES, m.T, rule=sink_allowed_rule)

    def objective_rule(mm):
        total = 0.0
        for t in mm.T:
            df = (1.0 + prices.discount_rate_per_period) ** (-t)
            oil = sum(mm.sink[node, Commodity.OIL.value, t] for node in sales)
            gas = sum(mm.sink[node, Commodity.GAS.value, t] for node in sales)
            water = sum(mm.sink[node, Commodity.WATER.value, t] for node in disposal)
            revenue = prices.oil * oil + prices.gas * gas - prices.water_disposal * water
            total += df * (revenue - mm.capital[t])
        return total

    m.obj = Objective(rule=objective_rule, sense=maximize)

    solver = get_highs_solver(tee=tee)
    result = solver.solve(m, tee=tee)
    from pyomo.opt import TerminationCondition

    tc = result.solver.termination_condition
    if tc not in {TerminationCondition.optimal, TerminationCondition.feasible}:
        raise RuntimeError(f"master problem did not solve optimally: {tc}")

    starts: list[StartDecision] = []
    for p in projects:
        for t in range(n):
            if value(m.x[p.id, t]) > 0.5:
                starts.append(StartDecision(p.id, t))
    plan = Plan(starts=tuple(starts))
    network = solve_network(model, plan, tee=tee)
    return OptimizeResult(
        plan=plan,
        network=network,
        objective=network.objective,
        solver="integrated",
        runtime_sec=time.perf_counter() - started,
    )
