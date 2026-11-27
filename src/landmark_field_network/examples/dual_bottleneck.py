"""Multi-period field with two shared bottlenecks and staggered expansions.

- Gas compressor base capacity fits roughly one pad.
- Oil takeaway base capacity fits roughly two pads.
- Compressor expansion may start in period 0 (lead 0).
- Oil-line loop expansion may start no earlier than period 3 (lead 0).
- Four pads with flat type curves; periods are monthly-style steps.
"""

from __future__ import annotations

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


def _flat_curve(oil: float, gas: float, water: float, periods: int) -> TypeCurve:
    return TypeCurve(
        oil=tuple(oil for _ in range(periods)),
        gas=tuple(gas for _ in range(periods)),
        water=tuple(water for _ in range(periods)),
    )


def build_dual_bottleneck(*, n_periods: int = 12, n_pads: int = 4) -> FieldModel:
    if n_pads < 2:
        raise ValueError("n_pads must be at least 2")
    pad_nodes = tuple(Node(f"pad_{i}", NodeKind.PAD) for i in range(n_pads))
    nodes = pad_nodes + (
        Node("ctb", NodeKind.CTB),
        Node("comp", NodeKind.COMPRESSOR),
        Node("sales", NodeKind.SALES),
        Node("swd", NodeKind.DISPOSAL),
    )
    arcs: list[Arc] = []
    for i in range(n_pads):
        pad = f"pad_{i}"
        arcs.extend(
            [
                Arc(f"{pad}_oil", pad, "ctb", Commodity.OIL, 5_000.0),
                Arc(f"{pad}_gas", pad, "ctb", Commodity.GAS, 5_000.0),
                Arc(f"{pad}_water", pad, "ctb", Commodity.WATER, 5_000.0),
            ]
        )
    arcs.extend(
        [
            # Oil takeaway bottleneck: base ~ 2 pads (80 oil each → 160).
            Arc("oil_takeaway", "ctb", "sales", Commodity.OIL, 160.0),
            Arc("ctb_gas", "ctb", "comp", Commodity.GAS, 5_000.0),
            Arc("ctb_water", "ctb", "swd", Commodity.WATER, 5_000.0),
            # Gas compressor bottleneck: base ~ 1 pad (120 gas).
            Arc("comp_gas", "comp", "sales", Commodity.GAS, 120.0),
        ]
    )
    curve = _flat_curve(oil=80.0, gas=120.0, water=30.0, periods=n_periods)
    projects: list[Project] = []
    for i in range(n_pads):
        projects.append(
            Project(
                id=f"pad_{i}",
                kind=ProjectKind.DEVELOPMENT,
                capital=(6_000.0,),
                pad_node=f"pad_{i}",
                type_curve=curve,
            )
        )
    projects.append(
        Project(
            id="comp_expand",
            kind=ProjectKind.FACILITY,
            capital=(10_000.0,),
            capacity_adds={"comp_gas": 240.0},
        )
    )
    projects.append(
        Project(
            id="oil_loop",
            kind=ProjectKind.FACILITY,
            capital=(9_000.0,),
            earliest_start=3,
            capacity_adds={"oil_takeaway": 200.0},
        )
    )
    return FieldModel(
        network=Network(nodes=nodes, arcs=tuple(arcs)),
        projects=tuple(projects),
        n_periods=n_periods,
        prices=Prices(
            oil=70.0,
            gas=3.5,
            water_disposal=1.0,
            discount_rate_per_period=0.008,
        ),
    )
