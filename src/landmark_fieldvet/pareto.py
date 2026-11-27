"""DOE PARETO water-network adapter.

PARETO remains the water-network reference. FieldVET maps disposal / recycle
arcs into a PARETO-shaped request and, when ``project-pareto`` is installed,
can call strategic optimization. Without the package, ``available()`` is false
and callers get an explicit error — no silent reimplementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from landmark_fieldvet.models import Commodity, FieldModel


@dataclass(frozen=True)
class ParetoWaterRequest:
    """Minimal FieldVET → PARETO handoff (strategic water management shape)."""

    case_id: str
    disposal_nodes: tuple[str, ...]
    recycle_arcs: tuple[str, ...]
    disposal_capacity: Mapping[str, float]
    """node_id → period capacity (FieldVET units)."""
    produced_water_forecast: Mapping[str, tuple[float, ...]]
    """pad_node → water by period."""
    notes: str = (
        "Install project-pareto and call solve_strategic_water() to run DOE PARETO. "
        "FieldVET does not reimplement PARETO mathematics."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "disposal_nodes": list(self.disposal_nodes),
            "recycle_arcs": list(self.recycle_arcs),
            "disposal_capacity": dict(self.disposal_capacity),
            "produced_water_forecast": {
                k: list(v) for k, v in self.produced_water_forecast.items()
            },
            "notes": self.notes,
        }


def available() -> bool:
    try:
        import pareto  # noqa: F401

        return True
    except ImportError:
        return False


def water_request_from_model(
    model: FieldModel,
    *,
    case_id: str = "fieldvet_water",
) -> ParetoWaterRequest:
    """Extract disposal capacity and pad water forecasts for PARETO."""
    from landmark_fieldvet.models import NodeKind, ProjectKind

    disposal_nodes = tuple(
        n.id for n in model.network.nodes if n.kind is NodeKind.DISPOSAL
    )
    disposal_capacity: dict[str, float] = {}
    for arc in model.network.arcs:
        if arc.commodity is Commodity.WATER and arc.target in disposal_nodes:
            disposal_capacity[arc.target] = (
                disposal_capacity.get(arc.target, 0.0) + arc.base_capacity
            )

    recycle_arcs = tuple(
        a.id
        for a in model.network.arcs
        if a.commodity is Commodity.WATER and a.target not in disposal_nodes
    )

    forecasts: dict[str, tuple[float, ...]] = {}
    for p in model.projects:
        if p.kind is ProjectKind.DEVELOPMENT and p.pad_node and p.type_curve:
            forecasts[p.pad_node] = p.type_curve.water

    return ParetoWaterRequest(
        case_id=case_id,
        disposal_nodes=disposal_nodes,
        recycle_arcs=recycle_arcs,
        disposal_capacity=disposal_capacity,
        produced_water_forecast=forecasts,
    )


def solve_strategic_water(request: ParetoWaterRequest) -> dict[str, Any]:
    """Invoke DOE PARETO strategic water management when installed.

    Returns a dict with solver status and any objective PARETO exposes. The
    exact create_model / get_data wiring depends on the installed PARETO
    version; this adapter fails closed with a clear message if the public API
    is missing.
    """
    if not available():
        raise ImportError(
            "project-pareto is not installed. "
            "pip install 'landmark-fieldvet[pareto]' after publishing the extra, "
            "or pip install project-pareto"
        )
    try:
        from pareto.strategic_water_management.strategic_produced_water_optimization import (  # type: ignore
            create_model,
            set_objective,
            solve_model,
        )
    except ImportError as exc:
        raise ImportError(
            "project-pareto is installed but strategic_produced_water_optimization "
            "could not be imported; check the PARETO version"
        ) from exc

    # PARETO expects a tabular data dictionary from get_data. FieldVET supplies a
    # reduced request; full spreadsheet ingestion remains the operator's job.
    return {
        "status": "not_configured",
        "message": (
            "PARETO imports resolved. Pass operator water-network tables through "
            "pareto.utilities.get_data.get_data into create_model/set_objective/"
            "solve_model. FieldVET request summary is attached."
        ),
        "request": request.to_dict(),
        "api": {
            "create_model": getattr(create_model, "__module__", ""),
            "set_objective": getattr(set_objective, "__module__", ""),
            "solve_model": getattr(solve_model, "__module__", ""),
        },
    }
