"""Turn capacity shadow prices into candidate facility projects.

``debottleneck_candidates`` ranks arcs. This module materializes those hints as
``Project`` rows that can be merged into a ``FieldModel`` inventory and re-run.
"""

from __future__ import annotations

from dataclasses import replace

from landmark_field_network.models import FieldModel, Project, ProjectKind
from landmark_field_network.network import NetworkResult, debottleneck_candidates


def propose_facility_projects(
    model: FieldModel,
    result: NetworkResult,
    *,
    expand_cost_per_unit: dict[str, float],
    capacity_add: float | dict[str, float] = 100.0,
    capital: float | dict[str, float] | None = None,
    id_prefix: str = "auto_expand",
) -> tuple[Project, ...]:
    """Create facility projects for arcs whose Σ dual exceeds expand cost.

    Parameters
    ----------
    expand_cost_per_unit:
        Cost of one unit of capacity on each arc (same units as shadow prices).
    capacity_add:
        Capacity added if the project is funded (scalar or per-arc).
    capital:
        Project capital. Defaults to ``expand_cost_per_unit[arc] * capacity_add``.
    """
    hits = debottleneck_candidates(result, expand_cost_per_unit=expand_cost_per_unit)
    existing = {p.id for p in model.projects}
    out: list[Project] = []
    for arc_id, _shadow, unit_cost in hits:
        pid = f"{id_prefix}_{arc_id}"
        if pid in existing:
            continue
        add = (
            float(capacity_add[arc_id])
            if isinstance(capacity_add, dict)
            else float(capacity_add)
        )
        if capital is None:
            cap = unit_cost * add
        elif isinstance(capital, dict):
            cap = float(capital[arc_id])
        else:
            cap = float(capital)
        out.append(
            Project(
                id=pid,
                kind=ProjectKind.FACILITY,
                capital=(cap,),
                capacity_adds={arc_id: add},
            )
        )
    return tuple(out)


def with_proposed_facilities(
    model: FieldModel,
    result: NetworkResult,
    *,
    expand_cost_per_unit: dict[str, float],
    capacity_add: float | dict[str, float] = 100.0,
    capital: float | dict[str, float] | None = None,
) -> FieldModel:
    """Return a new FieldModel with auto-generated facility projects appended."""
    proposed = propose_facility_projects(
        model,
        result,
        expand_cost_per_unit=expand_cost_per_unit,
        capacity_add=capacity_add,
        capital=capital,
    )
    if not proposed:
        return model
    return replace(model, projects=tuple(model.projects) + proposed)
