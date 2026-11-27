"""Minimal field where network effects are visible.

Two pads feed one compressor. Base compressor capacity fits one pad's peak gas
but not both. A facility project expands the compressor. Funding both pads
without the expansion cannibalizes; funding pad + expansion is complementary.
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


def build_toy_field(*, n_periods: int = 6) -> FieldModel:
    nodes = (
        Node("pad_a", NodeKind.PAD),
        Node("pad_b", NodeKind.PAD),
        Node("ctb", NodeKind.CTB),
        Node("comp", NodeKind.COMPRESSOR),
        Node("sales", NodeKind.SALES),
        Node("swd", NodeKind.DISPOSAL),
    )
    # Peak gas per pad = 100. Compressor base = 100 → one pad fits, two do not.
    arcs = (
        Arc("a_oil", "pad_a", "ctb", Commodity.OIL, 1_000.0),
        Arc("a_gas", "pad_a", "ctb", Commodity.GAS, 1_000.0),
        Arc("a_water", "pad_a", "ctb", Commodity.WATER, 1_000.0),
        Arc("b_oil", "pad_b", "ctb", Commodity.OIL, 1_000.0),
        Arc("b_gas", "pad_b", "ctb", Commodity.GAS, 1_000.0),
        Arc("b_water", "pad_b", "ctb", Commodity.WATER, 1_000.0),
        Arc("ctb_oil", "ctb", "sales", Commodity.OIL, 1_000.0),
        Arc("ctb_gas", "ctb", "comp", Commodity.GAS, 1_000.0),
        Arc("ctb_water", "ctb", "swd", Commodity.WATER, 1_000.0),
        Arc("comp_gas", "comp", "sales", Commodity.GAS, 100.0),
    )
    curve = _flat_curve(oil=50.0, gas=100.0, water=20.0, periods=n_periods)
    projects = (
        Project(
            id="pad_a",
            kind=ProjectKind.DEVELOPMENT,
            capital=(5_000.0,),
            pad_node="pad_a",
            type_curve=curve,
        ),
        Project(
            id="pad_b",
            kind=ProjectKind.DEVELOPMENT,
            capital=(5_000.0,),
            pad_node="pad_b",
            type_curve=curve,
        ),
        Project(
            id="comp_expand",
            kind=ProjectKind.FACILITY,
            capital=(8_000.0,),
            capacity_adds={"comp_gas": 100.0},
        ),
    )
    return FieldModel(
        network=Network(nodes=nodes, arcs=arcs),
        projects=projects,
        n_periods=n_periods,
        prices=Prices(oil=70.0, gas=3.0, water_disposal=1.0, discount_rate_per_period=0.01),
    )
