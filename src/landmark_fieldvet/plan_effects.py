"""Translate a fixed Plan into period production forecasts and arc capacities.

Timing is linear: production in period t is Σ_τ x(j,τ) · type_curve(t − τ − lead).
"""

from __future__ import annotations

from dataclasses import dataclass

from landmark_fieldvet.models import (
    Commodity,
    FieldModel,
    Plan,
    ProjectKind,
)


@dataclass(frozen=True)
class PlanEffects:
    """Period-indexed forecasts and capacities implied by a plan."""

    # pad_node -> commodity -> period -> volume
    forecast: dict[str, dict[Commodity, list[float]]]
    # arc_id -> period -> capacity
    capacity: dict[str, list[float]]
    # period -> capital spend
    capital: list[float]
    online_projects: tuple[str, ...]


def apply_plan(model: FieldModel, plan: Plan) -> PlanEffects:
    starts = plan.start_map()
    n = model.n_periods
    pads = {
        p.pad_node
        for p in model.projects
        if p.kind is ProjectKind.DEVELOPMENT and p.pad_node is not None
    }
    forecast: dict[str, dict[Commodity, list[float]]] = {
        pad: {c: [0.0] * n for c in Commodity} for pad in pads
    }
    capacity: dict[str, list[float]] = {
        a.id: [a.base_capacity] * n for a in model.network.arcs
    }
    capital = [0.0] * n
    online: list[str] = []

    for project in model.projects:
        if project.id not in starts:
            continue
        tau = starts[project.id]
        if tau < project.earliest_start:
            raise ValueError(
                f"{project.id} starts at {tau} before earliest_start "
                f"{project.earliest_start}"
            )
        online.append(project.id)
        for age, spend in enumerate(project.capital):
            t = tau + age
            if 0 <= t < n:
                capital[t] += spend

        online_from = tau + project.lead_time
        if project.kind is ProjectKind.DEVELOPMENT:
            if project.pad_node is None or project.type_curve is None:
                raise ValueError(f"development project {project.id} needs pad + curve")
            curve = project.type_curve
            pad = project.pad_node
            for t in range(max(0, online_from), n):
                age = t - online_from
                for commodity in Commodity:
                    forecast[pad][commodity][t] += curve.at(age, commodity)
        else:
            for arc_id, add in project.capacity_adds.items():
                if arc_id not in capacity:
                    raise ValueError(f"{project.id} adds capacity to unknown arc {arc_id}")
                for t in range(max(0, online_from), n):
                    capacity[arc_id][t] += add

    return PlanEffects(
        forecast=forecast,
        capacity=capacity,
        capital=capital,
        online_projects=tuple(online),
    )
