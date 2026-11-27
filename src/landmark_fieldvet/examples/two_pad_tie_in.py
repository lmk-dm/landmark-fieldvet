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

# --- Hydraulically derived constants (network-hydraulics two_pad fixture) ---
NOMINATED_MCF_D = 13_491.906708
BASE_MAX_EQUAL_MCF_D = 10_535.587006
UPGRADE_MAX_EQUAL_MCF_D = 21_170.597066
DAYS_PER_PERIOD = 30.0
# Shared gas capacity per period under base compressor (both pads competing).
BASE_SHARED_GAS_PER_PERIOD = 2.0 * BASE_MAX_EQUAL_MCF_D * DAYS_PER_PERIOD
UPGRADE_SHARED_GAS_PER_PERIOD = 2.0 * UPGRADE_MAX_EQUAL_MCF_D * DAYS_PER_PERIOD
PAD_GAS_PER_PERIOD = NOMINATED_MCF_D * DAYS_PER_PERIOD


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
    total_gas: float
    capital: float


def _first_gas(result: NetworkResult) -> int | None:
    earliest: int | None = None
    for pad in result.produced:
        for t, v in enumerate(result.produced[pad][Commodity.GAS]):
            if v > 1e-9 and (earliest is None or t < earliest):
                earliest = t
    return earliest


def _total_gas(result: NetworkResult) -> float:
    return sum(sum(result.produced[pad][Commodity.GAS]) for pad in result.produced)


def enumerate_tie_in_plans(
    model: FieldModel | None = None,
) -> list[EnumeratedPlan]:
    """Solve the handful of capital plans directly (no optimizer)."""
    model = model or build_two_pad_tie_in()
    candidates: list[tuple[str, Plan]] = [
        ("pad_a_only", Plan(starts=(StartDecision("pad_a", 0),))),
        ("pad_b_only", Plan(starts=(StartDecision("pad_b", 0),))),
        (
            "both_pads",
            Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))),
        ),
        (
            "both_pads_with_upgrade",
            Plan(
                starts=(
                    StartDecision("pad_a", 0),
                    StartDecision("pad_b", 0),
                    StartDecision("comp_expand", 0),
                )
            ),
        ),
    ]
    out: list[EnumeratedPlan] = []
    for name, plan in candidates:
        result = solve_network(model, plan)
        out.append(
            EnumeratedPlan(
                name=name,
                plan=plan,
                result=result,
                first_gas_period=_first_gas(result),
                total_gas=_total_gas(result),
                capital=sum(result.capital),
            )
        )
    return out


def preferred_plan(plans: list[EnumeratedPlan] | None = None) -> EnumeratedPlan:
    plans = plans or enumerate_tie_in_plans()
    return max(plans, key=lambda p: p.result.objective)


def compressor_capex_breakeven(
    *,
    lo: float = 0.0,
    hi: float = 50_000_000.0,
    tol: float = 1_000.0,
) -> float:
    """Largest compressor capital at which both+upgrade still beats both pads alone.

    Binary search on facility capital; pads fixed. Returns the switch point
    (above this, prefer both pads without the upgrade, or a single pad if that
    wins — here measured vs both_pads without expand).
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

    # If even free compressor loses, breakeven is lo.
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
