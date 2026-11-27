"""Two-pad gas tie-in decision priced in FieldVET.

Capacities are taken from ``network-hydraulics`` ``two_pad_gathering``
(``cargo run -p network-hydraulics --example dump_capacity``):

- nominated pad rate 3 kg/s ≈ 13,492 Mcf/d
- base equal-pad max ≈ 10,536 Mcf/d each (shared trunk / CTB limit)
- upgrade equal-pad max ≈ 21,171 Mcf/d each
- 48 h compressor outage undelivered ≈ 53,968 Mcf (NPV only if schedule recovers)

FieldVET still owns selection economics. Hydraulics owns whether a schedule's
rates are physically feasible; this example passes hydraulically derived arc
capacities so the economic ranking sees the same bottleneck.
"""

from __future__ import annotations

from dataclasses import dataclass

from landmark_fieldvet.models import (
    Arc,
    Commodity,
    FieldModel,
    Network,
    Node,
    NodeKind,
    Plan,
    Prices,
    Project,
    ProjectKind,
    StartDecision,
    TypeCurve,
)
from landmark_fieldvet.network import NetworkResult, solve_network
from landmark_fieldvet.plan_effects import apply_plan

# --- Hydraulically derived constants (network-hydraulics two_pad fixture) ---
NOMINATED_MCF_D = 13_491.906708
BASE_MAX_EQUAL_MCF_D = 10_535.587006
UPGRADE_MAX_EQUAL_MCF_D = 21_170.597066
DAYS_PER_PERIOD = 30.0
# Shared gas capacity per period under base compressor (both pads competing).
BASE_SHARED_GAS_PER_PERIOD = 2.0 * BASE_MAX_EQUAL_MCF_D * DAYS_PER_PERIOD
UPGRADE_SHARED_GAS_PER_PERIOD = 2.0 * UPGRADE_MAX_EQUAL_MCF_D * DAYS_PER_PERIOD
PAD_GAS_PER_PERIOD = NOMINATED_MCF_D * DAYS_PER_PERIOD

# Default deferral for "second pad later" plans (periods).
DEFAULT_DEFER_PERIODS = 6


def _flat_gas(periods: int, gas: float) -> TypeCurve:
    return TypeCurve(
        oil=tuple(0.0 for _ in range(periods)),
        gas=tuple(gas for _ in range(periods)),
        water=tuple(0.0 for _ in range(periods)),
    )


def build_two_pad_tie_in(
    *,
    n_periods: int = 12,
    pad_capital: float = 5_000_000.0,
    # Default sits below the operating-NPV lift from clearing curtailment so the
    # upgrade wins; compressor_capex_breakeven() finds the switch point.
    compressor_capital: float = 5_000_000.0,
    gas_price: float = 3.5,
    discount_rate_per_period: float = 0.008,
) -> FieldModel:
    """Field model whose shared gas capacity comes from the hydraulic study."""
    nodes = (
        Node("pad_a", NodeKind.PAD),
        Node("pad_b", NodeKind.PAD),
        Node("ctb", NodeKind.CTB),
        Node("comp", NodeKind.COMPRESSOR),
        Node("sales", NodeKind.SALES),
    )
    arcs = (
        Arc("a_gas", "pad_a", "ctb", Commodity.GAS, 1.0e12),
        Arc("b_gas", "pad_b", "ctb", Commodity.GAS, 1.0e12),
        Arc("trunk_gas", "ctb", "comp", Commodity.GAS, 1.0e12),
        Arc(
            "comp_gas",
            "comp",
            "sales",
            Commodity.GAS,
            BASE_SHARED_GAS_PER_PERIOD,
        ),
    )
    curve = _flat_gas(n_periods, PAD_GAS_PER_PERIOD)
    projects = (
        Project(
            id="pad_a",
            kind=ProjectKind.DEVELOPMENT,
            capital=(pad_capital,),
            pad_node="pad_a",
            type_curve=curve,
        ),
        Project(
            id="pad_b",
            kind=ProjectKind.DEVELOPMENT,
            capital=(pad_capital,),
            pad_node="pad_b",
            type_curve=curve,
        ),
        Project(
            id="comp_expand",
            kind=ProjectKind.FACILITY,
            capital=(compressor_capital,),
            capacity_adds={
                "comp_gas": UPGRADE_SHARED_GAS_PER_PERIOD - BASE_SHARED_GAS_PER_PERIOD
            },
        ),
    )
    return FieldModel(
        network=Network(nodes=nodes, arcs=arcs),
        projects=projects,
        n_periods=n_periods,
        prices=Prices(
            oil=0.0,
            gas=gas_price,
            water_disposal=0.0,
            discount_rate_per_period=discount_rate_per_period,
        ),
    )


@dataclass(frozen=True)
class EnumeratedPlan:
    name: str
    plan: Plan
    result: NetworkResult
    first_gas_period: int | None
    second_pad_period: int | None
    total_gas: float
    capital: float
    hydraulic_ok: bool
    hydraulic_notes: tuple[str, ...]


@dataclass(frozen=True)
class TieInDecision:
    """Asset-team answer for the first gas gathering tie-in case."""

    preferred: EnumeratedPlan
    plans: tuple[EnumeratedPlan, ...]
    which_pads: str
    when: str
    compressor_worth_buying: bool
    compressor_capex_breakeven: float
    what_limits_second_pad: str


def _first_gas(result: NetworkResult) -> int | None:
    earliest: int | None = None
    for pad in result.produced:
        for t, v in enumerate(result.produced[pad][Commodity.GAS]):
            if v > 1e-9 and (earliest is None or t < earliest):
                earliest = t
    return earliest


def _second_pad_start(plan: Plan) -> int | None:
    starts = {
        s.project_id: s.start_period
        for s in plan.starts
        if s.project_id in {"pad_a", "pad_b"}
    }
    if len(starts) < 2:
        return None
    return max(starts.values())


def _total_gas(result: NetworkResult) -> float:
    return sum(sum(result.produced[pad][Commodity.GAS]) for pad in result.produced)


def verify_schedule_against_hydraulics(
    model: FieldModel,
    plan: Plan,
    result: NetworkResult,
) -> tuple[bool, tuple[str, ...]]:
    """Check each period's delivered gas against hydraulically derived capacity.

    Uses the same ``comp_gas`` capacity series FieldVET applied (base vs upgrade
    online). A schedule that exceeds that capacity is not an actionable plan.
    """
    effects = apply_plan(model, plan)
    notes: list[str] = []
    ok = True
    for t in range(model.n_periods):
        delivered = sum(result.produced[pad][Commodity.GAS][t] for pad in result.produced)
        cap = effects.capacity["comp_gas"][t]
        if delivered > cap + 1e-6:
            ok = False
            notes.append(
                f"period {t}: delivered gas {delivered:.3f} exceeds hydraulic "
                f"shared capacity {cap:.3f}"
            )
    if ok:
        notes.append("all periods within hydraulically derived shared capacity")
    return ok, tuple(notes)


def _candidate_plans(*, defer: int) -> list[tuple[str, Plan]]:
    return [
        ("pad_a_only", Plan(starts=(StartDecision("pad_a", 0),))),
        ("pad_b_only", Plan(starts=(StartDecision("pad_b", 0),))),
        (
            "both_pads_t0",
            Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
        ),
        (
            "both_pads_with_upgrade_t0",
            Plan(
                starts=(
                    StartDecision("pad_a", 0),
                    StartDecision("pad_b", 0),
                    StartDecision("comp_expand", 0),
                )
            ),
        ),
        (
            f"pad_a_t0_pad_b_t{defer}",
            Plan(
                starts=(
                    StartDecision("pad_a", 0),
                    StartDecision("pad_b", defer),
                )
            ),
        ),
        (
            f"pad_b_t0_pad_a_t{defer}",
            Plan(
                starts=(
                    StartDecision("pad_b", 0),
                    StartDecision("pad_a", defer),
                )
            ),
        ),
        (
            f"pad_a_t0_pad_b_t{defer}_upgrade_t{defer}",
            Plan(
                starts=(
                    StartDecision("pad_a", 0),
                    StartDecision("pad_b", defer),
                    StartDecision("comp_expand", defer),
                )
            ),
        ),
        (
            f"both_pads_t0_upgrade_t{defer}",
            Plan(
                starts=(
                    StartDecision("pad_a", 0),
                    StartDecision("pad_b", 0),
                    StartDecision("comp_expand", defer),
                )
            ),
        ),
    ]


def enumerate_tie_in_plans(
    model: FieldModel | None = None,
    *,
    defer_periods: int = DEFAULT_DEFER_PERIODS,
) -> list[EnumeratedPlan]:
    """Solve the capital and timing plans directly (no optimizer)."""
    model = model or build_two_pad_tie_in()
    if defer_periods < 0 or defer_periods >= model.n_periods:
        raise ValueError("defer_periods must fall inside the model horizon")

    out: list[EnumeratedPlan] = []
    for name, plan in _candidate_plans(defer=defer_periods):
        result = solve_network(model, plan)
        hydraulic_ok, notes = verify_schedule_against_hydraulics(model, plan, result)
        out.append(
            EnumeratedPlan(
                name=name,
                plan=plan,
                result=result,
                first_gas_period=_first_gas(result),
                second_pad_period=_second_pad_start(plan),
                total_gas=_total_gas(result),
                capital=sum(result.capital),
                hydraulic_ok=hydraulic_ok,
                hydraulic_notes=notes,
            )
        )
    return out


def preferred_plan(plans: list[EnumeratedPlan] | None = None) -> EnumeratedPlan:
    plans = plans or enumerate_tie_in_plans()
    feasible = [p for p in plans if p.hydraulic_ok]
    pool = feasible or plans
    return max(pool, key=lambda p: p.result.objective)


def compressor_capex_breakeven(
    *,
    lo: float = 0.0,
    hi: float = 50_000_000.0,
    tol: float = 1_000.0,
) -> float:
    """Largest compressor capital at which both+upgrade still beats both pads alone.

    Binary search on facility capital; pads fixed. Returns the switch point
    (above this, prefer both pads without the upgrade).
    """

    def both_with(capex: float) -> float:
        model = build_two_pad_tie_in(compressor_capital=capex)
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
        return result.objective

    model0 = build_two_pad_tie_in()
    both_only = solve_network(
        model0,
        Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
    ).objective

    if both_with(lo) < both_only:
        return lo
    if both_with(hi) >= both_only:
        return hi

    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if both_with(mid) >= both_only:
            lo = mid
        else:
            hi = mid
    return lo


def tie_in_decision(
    *,
    defer_periods: int = DEFAULT_DEFER_PERIODS,
    compressor_capital: float | None = None,
) -> TieInDecision:
    """Answer which pads, when, and whether the compressor is worth buying."""
    kwargs = {}
    if compressor_capital is not None:
        kwargs["compressor_capital"] = compressor_capital
    model = build_two_pad_tie_in(**kwargs)
    plans = tuple(enumerate_tie_in_plans(model, defer_periods=defer_periods))
    pref = preferred_plan(list(plans))
    be = compressor_capex_breakeven()
    default_capex = model.project_by_id()["comp_expand"].capital[0]
    upgrade_in_pref = any(s.project_id == "comp_expand" for s in pref.plan.starts)

    starts = {s.project_id: s.start_period for s in pref.plan.starts}
    if "pad_a" in starts and "pad_b" in starts:
        if starts["pad_a"] == starts["pad_b"]:
            when = (
                f"bring both pads online in period {starts['pad_a']}"
                + (
                    f"; compressor expansion in period {starts['comp_expand']}"
                    if upgrade_in_pref
                    else " without compressor expansion"
                )
            )
        else:
            first = "pad_a" if starts["pad_a"] < starts["pad_b"] else "pad_b"
            second = "pad_b" if first == "pad_a" else "pad_a"
            when = (
                f"bring {first} online in period {starts[first]}, "
                f"{second} in period {starts[second]}"
            )
            if upgrade_in_pref:
                when += f"; compressor expansion in period {starts['comp_expand']}"
        which = "both pads"
    elif "pad_a" in starts:
        which = "pad_a only"
        when = f"bring pad_a online in period {starts['pad_a']}"
    else:
        which = "pad_b only"
        when = f"bring pad_b online in period {starts['pad_b']}"

    return TieInDecision(
        preferred=pref,
        plans=plans,
        which_pads=which,
        when=when,
        compressor_worth_buying=upgrade_in_pref and default_capex <= be,
        compressor_capex_breakeven=be,
        what_limits_second_pad=(
            "shared CTB / trunk pressure: both pads at nomination exceed the "
            "base compressor hydraulic ceiling and must curtail unless the "
            "upgrade is online"
        ),
    )
