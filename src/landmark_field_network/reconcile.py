"""Fiscal reconcile of a Field Network plan through landmark-economics.

Field Network's linear netbacks stay provisional. This module maps an
``EconomicsHandoff`` onto ``landmark_economics.dcf.run_dcf_from_forecast`` and
returns project- and portfolio-level fiscal NPV for comparison.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from landmark_field_network.export import EconomicsHandoff, ExportedProject, economics_project_list
from landmark_field_network.models import FieldModel, Plan
from landmark_field_network.network import NetworkResult


@dataclass(frozen=True)
class ProjectFiscalResult:
    project_id: str
    npv_fiscal: float
    npv_linear_share: float
    capital: float
    engine: str


@dataclass(frozen=True)
class FiscalReconcileReport:
    case_id: str
    portfolio_npv_linear: float
    portfolio_npv_fiscal: float
    delta: float
    """fiscal − linear (positive means fiscal is higher)."""
    projects: tuple[ProjectFiscalResult, ...]
    engine: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "portfolio_npv_linear": self.portfolio_npv_linear,
            "portfolio_npv_fiscal": self.portfolio_npv_fiscal,
            "delta": self.delta,
            "engine": self.engine,
            "notes": self.notes,
            "projects": [
                {
                    "project_id": p.project_id,
                    "npv_fiscal": p.npv_fiscal,
                    "npv_linear_share": p.npv_linear_share,
                    "capital": p.capital,
                    "engine": p.engine,
                }
                for p in self.projects
            ],
        }


def _ensure_landmark_economics() -> Any:
    try:
        import landmark_economics.dcf as dcf  # type: ignore

        return dcf
    except ImportError:
        pass
    # Workspace sibling: 50-decisions-economics/landmark-forecast/engines/economics
    here = Path(__file__).resolve()
    candidate = (
        here.parents[4]
        / "landmark-forecast"
        / "engines"
        / "economics"
    )
    # parents: reconcile.py → landmark_field_network → src → landmark-field-network → 50-decisions-economics
    alt = here.parents[3] / "landmark-forecast" / "engines" / "economics"
    for path in (alt, candidate):
        if (path / "landmark_economics" / "dcf.py").is_file():
            sys.path.insert(0, str(path))
            import landmark_economics.dcf as dcf  # type: ignore

            return dcf
    raise ImportError(
        "landmark_economics is required for fiscal reconcile; "
        "install the forecast economics package or run inside the Landmark workspace"
    )


def _project_fiscal_npv(
    dcf_mod: Any,
    project: ExportedProject,
    *,
    wi: float,
    royalty: float,
    case_start: date,
) -> float:
    capital = float(sum(project.capital))
    # Field Network periods are planning steps (often months). Feed them as months.
    params = dcf_mod.DcfParams(
        price_oil_bbl=project.oil_price,
        differential_bbl=0.0,
        gas_ngl_uplift_boe=0.0,
        fixed_loe_mo=0.0,
        variable_loe_boe=0.0,
        severance_tax=0.046,
        ad_valorem_tax=0.0,
        capex=capital,
        discount_rate=_annualize_discount(project.discount_rate_per_period),
        economic_limit_boed=0.0,
        n_months_max=max(len(project.oil_bbl), 1),
    )
    interest = dcf_mod.SimpleInterest(wi=wi, royalty=royalty)
    result = dcf_mod.run_dcf_from_forecast(
        project.oil_bbl,
        project.gas_mcf,
        project.water_bbl,
        params,
        interest,
        case_start=case_start,
        price_gas_mcf=project.gas_price,
        water_opex_bbl=project.water_disposal_price,
    )
    return float(result.npv)


def _annualize_discount(per_period: float) -> float:
    """Convert per-period discount to an annual rate assuming monthly periods."""
    if per_period <= -1.0:
        raise ValueError("discount_rate_per_period must be > -1")
    # (1+r_period)^12 - 1
    return (1.0 + per_period) ** 12 - 1.0


def reconcile_handoff(
    handoff: EconomicsHandoff,
    *,
    wi: float = 1.0,
    royalty: float = 0.0,
    case_start: date | None = None,
) -> FiscalReconcileReport:
    """Run landmark-economics DCF on each exported development project."""
    dcf_mod = _ensure_landmark_economics()
    start = case_start or date(2026, 1, 1)
    rows: list[ProjectFiscalResult] = []
    # Linear share: allocate portfolio linear NPV by gas+oil BOE produced.
    totals = []
    for p in handoff.projects:
        boe = sum(p.oil_bbl) + sum(p.gas_mcf) / 6.0
        totals.append(max(boe, 0.0))
    boe_sum = sum(totals) or 1.0

    fiscal_sum = 0.0
    for p, boe in zip(handoff.projects, totals, strict=True):
        npv = _project_fiscal_npv(dcf_mod, p, wi=wi, royalty=royalty, case_start=start)
        fiscal_sum += npv
        rows.append(
            ProjectFiscalResult(
                project_id=p.project_id,
                npv_fiscal=npv,
                npv_linear_share=handoff.portfolio_npv_linear * (boe / boe_sum),
                capital=float(sum(p.capital)),
                engine="landmark_economics.dcf.run_dcf_from_forecast",
            )
        )

    # Facility capital is in the linear objective but not in development DCF rows;
    # subtract facility capital PV already reflected in handoff linear NPV via note.
    return FiscalReconcileReport(
        case_id=handoff.case_id,
        portfolio_npv_linear=handoff.portfolio_npv_linear,
        portfolio_npv_fiscal=fiscal_sum,
        delta=fiscal_sum - handoff.portfolio_npv_linear,
        projects=tuple(rows),
        engine="landmark_economics",
        notes=(
            "Development projects reconciled via landmark-economics volume DCF. "
            "Facility capital remains in Field Network linear NPV only; full ARIES deck "
            "reconcile is a follow-on for reported reserves economics."
        ),
    )


def reconcile_plan(
    model: FieldModel,
    plan: Plan,
    network: NetworkResult,
    *,
    case_id: str = "field-network_plan",
    wi: float = 1.0,
    royalty: float = 0.0,
    case_start: date | None = None,
) -> FiscalReconcileReport:
    handoff = economics_project_list(model, plan, network, case_id=case_id)
    return reconcile_handoff(handoff, wi=wi, royalty=royalty, case_start=case_start)
