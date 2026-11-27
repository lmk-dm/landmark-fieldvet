"""Plan export for downstream economics — not fiscal reconciliation.

FieldVET's linear netbacks stay provisional. This module emits the selected
projects, timing, and produced volume paths in a shape a DCF owner can consume
(``landmark-economics`` / ARIES adapter). Calling the DCF kernel is a separate
milestone; this only preserves the investment decision and its volumes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from landmark_fieldvet.models import Commodity, FieldModel, Plan, ProjectKind
from landmark_fieldvet.network import NetworkResult


@dataclass(frozen=True)
class ExportedProject:
    project_id: str
    kind: str
    start_period: int
    capital: list[float]
    oil_bbl: list[float]
    gas_mcf: list[float]
    water_bbl: list[float]
    oil_price: float
    gas_price: float
    water_disposal_price: float
    discount_rate_per_period: float


@dataclass(frozen=True)
class EconomicsHandoff:
    """ARIES-compatible *project list* handoff (volumes + timing + prices)."""

    case_id: str
    n_periods: int
    portfolio_npv_linear: float
    projects: tuple[ExportedProject, ...]
    facility_starts: tuple[dict[str, Any], ...]
    notes: str = (
        "Linear FieldVET NPV is provisional. Reconcile through "
        "landmark-economics / ARIES before reporting."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "n_periods": self.n_periods,
            "portfolio_npv_linear": self.portfolio_npv_linear,
            "notes": self.notes,
            "facility_starts": list(self.facility_starts),
            "projects": [asdict(p) for p in self.projects],
        }

    def write_json(self, path: str | Path) -> Path:
        out = Path(path)
        out.write_text(json.dumps(self.to_dict(), indent=2))
        return out


def economics_project_list(
    model: FieldModel,
    plan: Plan,
    network: NetworkResult,
    *,
    case_id: str = "fieldvet_plan",
) -> EconomicsHandoff:
    """Build the downstream project list from a solved plan + network result."""
    starts = plan.start_map()
    by_id = model.project_by_id()
    exported: list[ExportedProject] = []
    facilities: list[dict[str, Any]] = []

    for project_id, tau in sorted(starts.items(), key=lambda kv: (kv[1], kv[0])):
        project = by_id[project_id]
        if project.kind is ProjectKind.DEVELOPMENT:
            pad = project.pad_node
            assert pad is not None
            exported.append(
                ExportedProject(
                    project_id=project_id,
                    kind=project.kind.value,
                    start_period=tau,
                    capital=list(project.capital),
                    oil_bbl=list(network.produced[pad][Commodity.OIL]),
                    gas_mcf=list(network.produced[pad][Commodity.GAS]),
                    water_bbl=list(network.produced[pad][Commodity.WATER]),
                    oil_price=model.prices.oil,
                    gas_price=model.prices.gas,
                    water_disposal_price=model.prices.water_disposal,
                    discount_rate_per_period=model.prices.discount_rate_per_period,
                )
            )
        else:
            facilities.append(
                {
                    "project_id": project_id,
                    "kind": project.kind.value,
                    "start_period": tau,
                    "capital": list(project.capital),
                    "capacity_adds": dict(project.capacity_adds),
                    "lead_time": project.lead_time,
                }
            )

    return EconomicsHandoff(
        case_id=case_id,
        n_periods=model.n_periods,
        portfolio_npv_linear=network.objective,
        projects=tuple(exported),
        facility_starts=tuple(facilities),
    )
