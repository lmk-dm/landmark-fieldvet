"""Hindcast / public-data validation scaffold.

Version 1 validates a *fixed* development plan against reported period
production (RRC-shaped CSV). It does not scrape the Railroad Commission; the
operator or a separate ingest job supplies the table.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from landmark_fieldvet.models import Commodity, FieldModel, Plan
from landmark_fieldvet.network import solve_network


@dataclass(frozen=True)
class HindcastRow:
    period: int
    oil_bbl: float
    gas_mcf: float
    water_bbl: float


@dataclass(frozen=True)
class HindcastReport:
    n_periods: int
    oil_mape: float
    gas_mape: float
    water_mape: float
    oil_within_tol: bool
    gas_within_tol: bool
    water_within_tol: bool
    tol: float
    notes: str

    @property
    def passed(self) -> bool:
        return self.oil_within_tol and self.gas_within_tol and self.water_within_tol

    def to_dict(self) -> dict:
        return {
            "n_periods": self.n_periods,
            "oil_mape": self.oil_mape,
            "gas_mape": self.gas_mape,
            "water_mape": self.water_mape,
            "oil_within_tol": self.oil_within_tol,
            "gas_within_tol": self.gas_within_tol,
            "water_within_tol": self.water_within_tol,
            "tol": self.tol,
            "passed": self.passed,
            "notes": self.notes,
        }


def load_reported_production_csv(path: str | Path) -> tuple[HindcastRow, ...]:
    """Load CSV with columns: period,oil_bbl,gas_mcf,water_bbl."""
    rows: list[HindcastRow] = []
    with Path(path).open(newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append(
                HindcastRow(
                    period=int(raw["period"]),
                    oil_bbl=float(raw["oil_bbl"]),
                    gas_mcf=float(raw["gas_mcf"]),
                    water_bbl=float(raw["water_bbl"]),
                )
            )
    rows.sort(key=lambda r: r.period)
    return tuple(rows)


def _mape(actual: list[float], predicted: list[float]) -> float:
    errs = []
    for a, p in zip(actual, predicted, strict=True):
        denom = abs(a) if abs(a) > 1e-9 else 1.0
        errs.append(abs(a - p) / denom)
    return sum(errs) / len(errs) if errs else 0.0


def validate_fixed_plan(
    model: FieldModel,
    plan: Plan,
    reported: Sequence[HindcastRow],
    *,
    tol: float = 0.15,
) -> HindcastReport:
    """Compare network-subproblem totals to reported production.

    ``tol`` is maximum allowed MAPE (e.g. 0.15 = 15%).
    """
    result = solve_network(model, plan)
    n = min(model.n_periods, len(reported))
    oil_a = [reported[t].oil_bbl for t in range(n)]
    gas_a = [reported[t].gas_mcf for t in range(n)]
    water_a = [reported[t].water_bbl for t in range(n)]
    oil_p = [
        sum(result.produced[pad][Commodity.OIL][t] for pad in result.produced)
        for t in range(n)
    ]
    gas_p = [
        sum(result.produced[pad][Commodity.GAS][t] for pad in result.produced)
        for t in range(n)
    ]
    water_p = [
        sum(result.produced[pad][Commodity.WATER][t] for pad in result.produced)
        for t in range(n)
    ]
    oil_m = _mape(oil_a, oil_p)
    gas_m = _mape(gas_a, gas_p)
    water_m = _mape(water_a, water_p)
    return HindcastReport(
        n_periods=n,
        oil_mape=oil_m,
        gas_mape=gas_m,
        water_mape=water_m,
        oil_within_tol=oil_m <= tol,
        gas_within_tol=gas_m <= tol,
        water_within_tol=water_m <= tol,
        tol=tol,
        notes=(
            "Fixed-plan network validation against supplied reported production. "
            "RRC ingest is out of band; feed a CSV built from public or operator data."
        ),
    )
