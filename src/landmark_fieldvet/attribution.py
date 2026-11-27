"""Four views of project value.

Standalone, marginal-in-plan, pairwise interaction, and sampled Shapley.
Shapley shares are the only view that sums exactly to portfolio NPV (in
expectation over the sampled orderings).
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from landmark_fieldvet.models import FieldModel, Plan, StartDecision
from landmark_fieldvet.network import NetworkResult, solve_network


@dataclass(frozen=True)
class AttributionReport:
    portfolio_npv: float
    standalone: dict[str, float]
    marginal: dict[str, float]
    interaction: dict[tuple[str, str], float]
    shapley: dict[str, float]
    shapley_samples: int


def _plan_of(starts: dict[str, int]) -> Plan:
    return Plan(
        starts=tuple(
            StartDecision(project_id=j, start_period=tau) for j, tau in sorted(starts.items())
        )
    )


def _npv(model: FieldModel, starts: dict[str, int]) -> float:
    return solve_network(model, _plan_of(starts)).objective


def attribute(
    model: FieldModel,
    plan: Plan,
    *,
    shapley_samples: int = 64,
    seed: int = 0,
    portfolio_result: NetworkResult | None = None,
    include_interaction: bool | None = None,
    include_shapley: bool = True,
) -> AttributionReport:
    starts = plan.start_map()
    ids = list(starts.keys())
    portfolio = (
        portfolio_result.objective
        if portfolio_result is not None
        else _npv(model, starts)
    )
    empty = _npv(model, {})

    standalone: dict[str, float] = {}
    for j in ids:
        standalone[j] = _npv(model, {j: starts[j]}) - empty

    marginal: dict[str, float] = {}
    for j in ids:
        without = {k: v for k, v in starts.items() if k != j}
        marginal[j] = portfolio - _npv(model, without)

    # Pairwise interaction is O(n²) network solves; skip by default on large plans.
    if include_interaction is None:
        include_interaction = len(ids) <= 8
    interaction: dict[tuple[str, str], float] = {}
    if include_interaction:
        for a, b in itertools.combinations(ids, 2):
            both = _npv(model, {a: starts[a], b: starts[b]})
            only_a = _npv(model, {a: starts[a]})
            only_b = _npv(model, {b: starts[b]})
            # v({a,b}) - v({a}) - v({b}) + v({})
            interaction[(a, b)] = both - only_a - only_b + empty

    shapley: dict[str, float] = {}
    samples_used = 0
    if include_shapley:
        samples_used = shapley_samples
        shapley = _sample_shapley(
            model, starts, samples=shapley_samples, seed=seed, empty=empty
        )

    return AttributionReport(
        portfolio_npv=portfolio,
        standalone=standalone,
        marginal=marginal,
        interaction=interaction,
        shapley=shapley,
        shapley_samples=samples_used,
    )


def _sample_shapley(
    model: FieldModel,
    starts: dict[str, int],
    *,
    samples: int,
    seed: int,
    empty: float,
) -> dict[str, float]:
    ids = list(starts.keys())
    if not ids:
        return {}
    if samples <= 0:
        raise ValueError("shapley_samples must be positive")

    rng = random.Random(seed)
    totals = {j: 0.0 for j in ids}
    # Exact enumeration when n! is small.
    if len(ids) <= 6:
        orderings = list(itertools.permutations(ids))
    else:
        orderings = [tuple(rng.sample(ids, len(ids))) for _ in range(samples)]

    for order in orderings:
        running: dict[str, int] = {}
        prev = empty
        for j in order:
            running[j] = starts[j]
            now = _npv(model, running)
            totals[j] += now - prev
            prev = now

    denom = float(len(orderings))
    return {j: totals[j] / denom for j in ids}
