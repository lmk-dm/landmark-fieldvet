"""Mature conventional shared-injection capacity for Reference Energy.

Mirrors the toy gas pattern: many floods share one water trunk. Base capacity
fits a few floods; facility projects expand the trunk. Landmark Capital imports
the base spare water; facility Candidates carry water_add_bwpd and NPV = −capital.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from landmark_field_network.export import economics_project_list
from landmark_field_network.master import optimize_portfolio
from landmark_field_network.models import (
    Arc,
    Commodity,
    FieldModel,
    Network,
    Node,
    NodeKind,
    Prices,
    Project,
    ProjectKind,
    TypeCurve,
)
from landmark_field_network.reconcile import reconcile_plan

BASE_INJECT_BWPD = 20_000.0
FACILITY_ADD_BWPD = 20_000.0


def _curve(oil: float, gas: float, water: float, periods: int) -> TypeCurve:
    return TypeCurve(
        oil=tuple(oil for _ in range(periods)),
        gas=tuple(gas for _ in range(periods)),
        water=tuple(water for _ in range(periods)),
    )


def build_mature_water(*, n_periods: int = 6, n_floods: int = 8) -> FieldModel:
    nodes: list[Node] = [
        Node("hub", NodeKind.CTB),
        Node("inject", NodeKind.COMPRESSOR),
        Node("sales", NodeKind.SALES),
        Node("swd", NodeKind.DISPOSAL),
    ]
    arcs: list[Arc] = [
        Arc("hub_oil", "hub", "sales", Commodity.OIL, 1_000_000.0),
        Arc("hub_gas", "hub", "sales", Commodity.GAS, 1_000_000.0),
        Arc("hub_water", "hub", "inject", Commodity.WATER, 1_000_000.0),
        Arc("inject_water", "inject", "swd", Commodity.WATER, BASE_INJECT_BWPD),
    ]
    projects: list[Project] = []
    for index in range(1, n_floods + 1):
        pad = f"flood_{index:03d}"
        nodes.append(Node(pad, NodeKind.PAD))
        arcs.extend(
            [
                Arc(f"{pad}_oil", pad, "hub", Commodity.OIL, 1_000_000.0),
                Arc(f"{pad}_gas", pad, "hub", Commodity.GAS, 1_000_000.0),
                Arc(f"{pad}_water", pad, "hub", Commodity.WATER, 1_000_000.0),
            ]
        )
        projects.append(
            Project(
                id=f"waterflood-{index:03d}",
                kind=ProjectKind.DEVELOPMENT,
                capital=(5_000_000.0,),
                pad_node=pad,
                type_curve=_curve(oil=200.0, gas=80.0, water=5_000.0, periods=n_periods),
            )
        )
    for index in range(1, 5):
        projects.append(
            Project(
                id=f"water-injection-facility-{index:03d}",
                kind=ProjectKind.FACILITY,
                capital=(5_000_000.0 + index * 200_000.0,),
                capacity_adds={"inject_water": FACILITY_ADD_BWPD},
            )
        )
    return FieldModel(
        network=Network(nodes=tuple(nodes), arcs=tuple(arcs)),
        projects=tuple(projects),
        n_periods=n_periods,
        prices=Prices(oil=75.0, gas=3.0, water_disposal=0.5, discount_rate_per_period=0.008),
    )


def export_capacity_contract(model: FieldModel | None = None) -> dict[str, Any]:
    model = model or build_mature_water()
    base_water = 0.0
    for arc in model.network.arcs:
        if arc.id == "inject_water":
            base_water += float(arc.base_capacity)
    return {
        "asset": "Mature conventional",
        "country": "US",
        "state": "TX",
        "admin1_key": "US-TX",
        "spare_gas_mscfd": 0.0,
        "spare_water_bwpd": base_water,
        "source": "landmark-field-network.examples.mature_water",
        "synthetic": True,
        "notes": (
            "Spare water is the base inject_water arc capacity. Facility Candidates "
            "in landmark-capital add water_add_bwpd; do not inflate spare by those adds."
        ),
    }


def export_for_capital(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    model = build_mature_water()
    capacity_path = out_dir / "mature_conventional_capacity.json"
    capacity_path.write_text(json.dumps(export_capacity_contract(model), indent=2) + "\n")
    opt = optimize_portfolio(model)
    handoff = economics_project_list(
        model, opt.plan, opt.network, case_id="mature_conventional_ref"
    )
    handoff_path = out_dir / "mature_conventional_handoff.json"
    handoff.write_json(handoff_path)
    paths = {
        "capacity": capacity_path,
        "handoff": handoff_path,
    }
    try:
        report = reconcile_plan(model, opt.plan, opt.network, case_id="mature_conventional_ref")
        reconcile_path = out_dir / "mature_conventional_reconcile.json"
        reconcile_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
        paths["reconcile"] = reconcile_path
    except ImportError:
        # Capacity + handoff are enough for landmark-capital spare-water wiring.
        pass
    return paths


__all__ = [
    "BASE_INJECT_BWPD",
    "FACILITY_ADD_BWPD",
    "build_mature_water",
    "export_capacity_contract",
    "export_for_capital",
]
