"""Benders decomposition for network-aware portfolio selection.

Master holds discrete starts ``x[j,τ]`` and an operating-NPV surrogate ``θ``.
Each candidate plan is evaluated by the fixed-plan network LP; capacity and
forecast duals yield a linear optimality cut on ``θ``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from pyomo.environ import (
    Binary,
    ConcreteModel,
    Constraint,
    ConstraintList,
    NonNegativeReals,
    Objective,
    RangeSet,
    Set,
    Var,
    maximize,
    value,
)
from pyomo.opt import TerminationCondition

from landmark_fieldvet.models import (
    Commodity,
    FieldModel,
    Plan,
    ProjectKind,
    StartDecision,
)
from landmark_fieldvet.network import NetworkResult, solve_network
from landmark_fieldvet.solvers import get_highs_solver


@dataclass(frozen=True)
class BendersStats:
    iterations: int
    runtime_sec: float
    lower_bound: float
    upper_bound: float
    gap: float
    cuts: int
    converged: bool


@dataclass(frozen=True)
class BendersResult:
    plan: Plan
    network: NetworkResult
    objective: float
    stats: BendersStats
    solver: str = "benders"


def _discount(model: FieldModel, t: int) -> float:
    return (1.0 + model.prices.discount_rate_per_period) ** (-t)


def _capacity_coeff(model: FieldModel, arc_id: str, t: int, project_id: str, tau: int) -> float:
    p = model.project_by_id()[project_id]
    if arc_id not in p.capacity_adds:
        return 0.0
    if tau + p.lead_time <= t:
        return p.capacity_adds[arc_id]
    return 0.0


def _forecast_coeff(
    model: FieldModel,
    pad: str,
    commodity: Commodity,
    t: int,
    project_id: str,
    tau: int,
) -> float:
    p = model.project_by_id()[project_id]
    if p.kind is not ProjectKind.DEVELOPMENT or p.pad_node != pad or p.type_curve is None:
        return 0.0
    age = t - (tau + p.lead_time)
    return p.type_curve.at(age, commodity)


def _capital_coeff(model: FieldModel, t: int, project_id: str, tau: int) -> float:
    p = model.project_by_id()[project_id]
    age = t - tau
    if 0 <= age < len(p.capital):
        return p.capital[age]
    return 0.0


def optimize_benders(
    model: FieldModel,
    *,
    tee: bool = False,
    max_iterations: int = 80,
    abs_tol: float = 1.0,
    rel_tol: float = 1e-4,
    time_limit_sec: float = 120.0,
) -> BendersResult:
    """Solve selection/timing by Benders with the network LP as subproblem."""
    started = time.perf_counter()
    n = model.n_periods
    projects = list(model.projects)
    arcs = list(model.network.arcs)
    pads = sorted(
        {
            p.pad_node
            for p in projects
            if p.kind is ProjectKind.DEVELOPMENT and p.pad_node is not None
        }
    )

    m = ConcreteModel(name="fieldvet_benders_master")
    m.T = RangeSet(0, n - 1)
    m.J = Set(initialize=[p.id for p in projects])
    m.x = Var(m.J, m.T, domain=Binary)
    m.theta = Var(domain=NonNegativeReals)
    m.cuts = ConstraintList()

    def one_start_rule(mm, j):
        return sum(mm.x[j, t] for t in mm.T) <= 1

    m.one_start = Constraint(m.J, rule=one_start_rule)

    def earliest_rule(mm, j, t):
        if t < model.project_by_id()[j].earliest_start:
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
            return sum(mm.x[j, t] for j in groups[g] for t in mm.T) <= 1

        m.group_excl = Constraint(m.GROUPS, rule=group_rule)

    extra = [(p.id, r, t) for p in projects for r in p.requires for t in range(n)]
    if extra:
        m.REQ = Set(initialize=extra, dimen=3)

        def requires_pair_rule(mm, j, r, t):
            return sum(mm.x[r, tau] for tau in mm.T if tau <= t) >= mm.x[j, t]

        m.requires_pair = Constraint(m.REQ, rule=requires_pair_rule)

    # Discounted capital as a linear expression in x
    def capital_npv_expr(mm):
        total = 0.0
        for t in mm.T:
            df = _discount(model, t)
            for p in projects:
                for tau in mm.T:
                    total += df * _capital_coeff(model, t, p.id, tau) * mm.x[p.id, tau]
        return total

    if model.capital_budget is not None:
        budgets = list(model.capital_budget)
        if len(budgets) != n:
            raise ValueError("capital_budget length must equal n_periods")

        def budget_rule(mm, t):
            spend = sum(
                _capital_coeff(model, t, p.id, tau) * mm.x[p.id, tau]
                for p in projects
                for tau in mm.T
            )
            return spend <= budgets[t]

        m.budget = Constraint(m.T, rule=budget_rule)

    m.obj = Objective(expr=m.theta - capital_npv_expr(m), sense=maximize)

    # θ upper bound: unrestricted optimistic operating NPV (all forecasts free).
    # Start with a loose big-M from prices × total possible production.
    rough = 0.0
    for p in projects:
        if p.kind is ProjectKind.DEVELOPMENT and p.type_curve is not None:
            rough += model.prices.oil * sum(p.type_curve.oil)
            rough += model.prices.gas * sum(p.type_curve.gas)
    m.theta.setub(max(rough, 1.0))

    solver = get_highs_solver(tee=tee)
    best_plan = Plan(starts=())
    best_network = solve_network(model, best_plan, include_capital=True)
    best_obj = best_network.objective
    lower = best_obj
    upper = float("inf")
    cuts = 0
    converged = False
    iteration = 0

    for iteration in range(1, max_iterations + 1):
        if time.perf_counter() - started > time_limit_sec:
            break
        result = solver.solve(m, tee=tee)
        tc = result.solver.termination_condition
        if tc not in {TerminationCondition.optimal, TerminationCondition.feasible}:
            raise RuntimeError(f"Benders master did not solve: {tc}")

        starts: dict[str, int] = {}
        for p in projects:
            for t in range(n):
                if value(m.x[p.id, t]) > 0.5:
                    starts[p.id] = t
        plan = Plan(
            starts=tuple(StartDecision(j, tau) for j, tau in sorted(starts.items()))
        )
        master_obj = float(value(m.obj))
        theta_hat = float(value(m.theta))
        upper = master_obj

        sub = solve_network(model, plan, tee=tee, include_capital=False)
        # Full NPV for incumbent tracking
        full = solve_network(model, plan, tee=tee, include_capital=True)
        if full.objective > lower + 1e-9:
            lower = full.objective
            best_plan = plan
            best_network = full
            best_obj = full.objective

        # Optimality cut on operating NPV: θ ≤ φ* + π·(Cap(x)-Cap*) + λ·(F(x)-F*)
        phi = sub.operating_npv
        cap_star = sub.effects.capacity
        f_star = sub.effects.forecast

        const = phi
        # Subtract π·Cap* and λ·F*
        for a in arcs:
            for t in range(n):
                const -= sub.shadow_price[a.id][t] * cap_star[a.id][t]
        for pad in pads:
            for c in Commodity:
                for t in range(n):
                    const -= sub.forecast_shadow[pad][c][t] * f_star[pad][c][t]

        # Linear terms in x
        expr = const
        for p in projects:
            for tau in range(n):
                coef = 0.0
                for a in arcs:
                    for t in range(n):
                        coef += sub.shadow_price[a.id][t] * _capacity_coeff(
                            model, a.id, t, p.id, tau
                        )
                if p.kind is ProjectKind.DEVELOPMENT and p.pad_node is not None:
                    for c in Commodity:
                        for t in range(n):
                            coef += sub.forecast_shadow[p.pad_node][c][t] * _forecast_coeff(
                                model, p.pad_node, c, t, p.id, tau
                            )
                # Base capacity is already in Cap*; only incremental via x.
                # Also add base capacity contribution into const already via Cap*.
                expr += coef * m.x[p.id, tau]

        # Base capacity is independent of x and was subtracted via Cap*; add it
        # back as part of π·Cap(x) where Cap(x)=base+adds(x). We subtracted
        # π·(base+adds*) and add π·adds(x), so we still need +π·base:
        base_term = 0.0
        for a in arcs:
            for t in range(n):
                base_term += sub.shadow_price[a.id][t] * a.base_capacity
        expr = expr + base_term

        m.cuts.add(m.theta <= expr)
        cuts += 1

        gap = upper - lower
        rel = gap / max(1.0, abs(upper)) if upper < float("inf") else float("inf")
        # Proven optimal when the master θ matches the subproblem at the
        # current integer plan (no violated optimality cut).
        if theta_hat <= phi + abs_tol:
            converged = True
            break
        if gap <= abs_tol or rel <= rel_tol:
            # Bound gap is small, but only certify if the current plan is cut-tight.
            if theta_hat <= phi + max(abs_tol, rel_tol * max(1.0, abs(phi))):
                converged = True
                break

    runtime = time.perf_counter() - started
    final_gap = (upper - lower) if upper < float("inf") else float("inf")
    stats = BendersStats(
        iterations=iteration,
        runtime_sec=runtime,
        lower_bound=lower,
        upper_bound=upper if upper < float("inf") else lower,
        gap=final_gap if upper < float("inf") else 0.0,
        cuts=cuts,
        converged=converged,
    )
    return BendersResult(
        plan=best_plan,
        network=best_network,
        objective=best_obj,
        stats=stats,
    )
