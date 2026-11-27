"""Benders decomposition for network-aware portfolio selection.

Master holds discrete starts ``x[j,τ]`` and an operating-NPV surrogate ``θ``.
Each candidate plan is evaluated by the fixed-plan network LP. Dual cuts on
capacity/forecast plus integer L-shaped cuts drive finite convergence.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

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


def _plan_key(starts: dict[str, int]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(starts.items()))


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
    start_times = model.allowed_starts()
    pads = sorted(
        {
            p.pad_node
            for p in projects
            if p.kind is ProjectKind.DEVELOPMENT and p.pad_node is not None
        }
    )

    m = ConcreteModel(name="fieldvet_benders_master")
    m.T = RangeSet(0, n - 1)
    m.TAU = Set(initialize=list(start_times))
    m.J = Set(initialize=[p.id for p in projects])
    m.x = Var(m.J, m.TAU, domain=Binary)
    m.theta = Var(domain=NonNegativeReals)
    m.cuts = ConstraintList()

    def one_start_rule(mm, j):
        return sum(mm.x[j, t] for t in mm.TAU) <= 1

    m.one_start = Constraint(m.J, rule=one_start_rule)

    def earliest_rule(mm, j, t):
        if t < model.project_by_id()[j].earliest_start:
            return mm.x[j, t] == 0
        return Constraint.Skip

    m.earliest = Constraint(m.J, m.TAU, rule=earliest_rule)

    if model.fix_to_earliest_start:
        def fix_earliest_rule(mm, j, t):
            if t != model.project_by_id()[j].earliest_start:
                return mm.x[j, t] == 0
            return Constraint.Skip

        m.fix_earliest = Constraint(m.J, m.TAU, rule=fix_earliest_rule)

    groups: dict[str, list[str]] = {}
    for p in projects:
        if p.group:
            groups.setdefault(p.group, []).append(p.id)
    if groups:
        m.GROUPS = Set(initialize=list(groups.keys()))

        def group_rule(mm, g):
            return sum(mm.x[j, t] for j in groups[g] for t in mm.TAU) <= 1

        m.group_excl = Constraint(m.GROUPS, rule=group_rule)

    extra = [(p.id, r, t) for p in projects for r in p.requires for t in start_times]
    if extra:
        m.REQ = Set(initialize=extra, dimen=3)

        def requires_pair_rule(mm, j, r, t):
            return sum(mm.x[r, tau] for tau in mm.TAU if tau <= t) >= mm.x[j, t]

        m.requires_pair = Constraint(m.REQ, rule=requires_pair_rule)

    def capital_npv_expr(mm):
        total = 0.0
        for t in mm.T:
            df = _discount(model, t)
            for p in projects:
                for tau in mm.TAU:
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
                for tau in mm.TAU
            )
            return spend <= budgets[t]

        m.budget = Constraint(m.T, rule=budget_rule)

    m.obj = Objective(expr=m.theta - capital_npv_expr(m), sense=maximize)

    rough = 0.0
    for p in projects:
        if p.kind is ProjectKind.DEVELOPMENT and p.type_curve is not None:
            rough += model.prices.oil * sum(p.type_curve.oil)
            rough += model.prices.gas * sum(p.type_curve.gas)
    theta_ub = max(rough, 1.0)
    m.theta.setub(theta_ub)

    best_plan = Plan(starts=())
    best_network = solve_network(model, best_plan, include_capital=True)
    best_obj = best_network.objective
    lower = best_obj
    upper = float("inf")
    cuts = 0
    converged = False
    iteration = 0
    seen: set[tuple[tuple[str, int], ...]] = set()

    for iteration in range(1, max_iterations + 1):
        remaining = time_limit_sec - (time.perf_counter() - started)
        if remaining <= 0:
            break
        # Selection-only masters are tiny — do not time-limit them (need a true UB).
        n_bin = len(projects) if model.fix_to_earliest_start else len(projects) * len(start_times)
        per_iter = None if n_bin <= 40 else min(20.0, max(3.0, remaining))
        solver = get_highs_solver(tee=tee, time_limit_sec=per_iter)
        result = solver.solve(m, tee=tee)
        tc = result.solver.termination_condition
        if tc not in {
            TerminationCondition.optimal,
            TerminationCondition.feasible,
            TerminationCondition.maxTimeLimit,
        }:
            raise RuntimeError(f"Benders master did not solve: {tc}")
        try:
            master_obj = float(value(m.obj))
            theta_hat = float(value(m.theta))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Benders master returned no incumbent: {tc}") from exc

        # Only an optimal master yields a true upper bound.
        if tc == TerminationCondition.optimal:
            upper = master_obj

        starts: dict[str, int] = {}
        for p in projects:
            for t in start_times:
                if value(m.x[p.id, t]) > 0.5:
                    starts[p.id] = t
        key = _plan_key(starts)
        plan = Plan(
            starts=tuple(StartDecision(j, tau) for j, tau in key)
        )

        full = solve_network(model, plan, tee=tee, include_capital=True)
        phi = full.operating_npv
        if full.objective > lower + 1e-9:
            lower = full.objective
            best_plan = plan
            best_network = full
            best_obj = full.objective

        # Dual optimality cut (valid supporting hyperplane in Cap/F).
        cap_star = full.effects.capacity
        f_star = full.effects.forecast
        const = phi
        for a in arcs:
            for t in range(n):
                const -= full.shadow_price[a.id][t] * cap_star[a.id][t]
        for pad in pads:
            for c in Commodity:
                for t in range(n):
                    const -= full.forecast_shadow[pad][c][t] * f_star[pad][c][t]

        expr = const
        for p in projects:
            for tau in start_times:
                coef = 0.0
                for a in arcs:
                    for t in range(n):
                        coef += full.shadow_price[a.id][t] * _capacity_coeff(
                            model, a.id, t, p.id, tau
                        )
                if p.kind is ProjectKind.DEVELOPMENT and p.pad_node is not None:
                    for c in Commodity:
                        for t in range(n):
                            coef += full.forecast_shadow[p.pad_node][c][t] * _forecast_coeff(
                                model, p.pad_node, c, t, p.id, tau
                            )
                expr += coef * m.x[p.id, tau]
        base_term = 0.0
        for a in arcs:
            for t in range(n):
                base_term += full.shadow_price[a.id][t] * a.base_capacity
        m.cuts.add(m.theta <= expr + base_term)
        cuts += 1

        # Integer L-shaped cut — excludes this binary plan.
        if key not in seen:
            seen.add(key)
            big_m = max(theta_ub - phi, abs(phi), 1.0)
            int_cut = phi
            for p in projects:
                for tau in start_times:
                    if starts.get(p.id) == tau:
                        int_cut = int_cut + big_m * (1 - m.x[p.id, tau])
                    else:
                        int_cut = int_cut + big_m * m.x[p.id, tau]
            m.cuts.add(m.theta <= int_cut)
            cuts += 1

        if theta_hat <= phi + abs_tol and tc == TerminationCondition.optimal:
            converged = True
            upper = min(upper, master_obj)
            break

        # Standard Benders stop: proven UB−LB within tolerance.
        if upper < float("inf") and tc == TerminationCondition.optimal:
            gap = upper - lower
            rel = gap / max(1.0, abs(upper))
            if gap <= abs_tol or rel <= rel_tol:
                converged = True
                break

    runtime = time.perf_counter() - started
    if upper < float("inf"):
        final_gap = upper - lower
        final_upper = upper
    else:
        final_gap = float("inf")
        final_upper = lower
    stats = BendersStats(
        iterations=iteration,
        runtime_sec=runtime,
        lower_bound=lower,
        upper_bound=final_upper,
        gap=0.0 if converged and final_gap == float("inf") else (
            final_gap if final_gap != float("inf") else 0.0
        ),
        cuts=cuts,
        converged=converged,
    )
    return BendersResult(
        plan=best_plan,
        network=best_network,
        objective=best_obj,
        stats=stats,
    )
