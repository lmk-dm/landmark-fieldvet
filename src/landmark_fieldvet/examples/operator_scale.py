"""20-pad / 5-facility area from the FieldVET v2 next-actions target.

Two gathering trains share a compressor and an oil takeaway trunk. A water
disposal node is also capacity-limited. Facility projects unlock capacity on a
staggered schedule. Each project starts at its earliest_start only (selection
with staggered timing) so Benders can certify the case.
"""

from __future__ import annotations

from landmark_fieldvet.models import (
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

N_PADS = 20
N_FACILITIES = 5


def _decline_curve(
    *,
    oil0: float,
    gas0: float,
    water0: float,
    periods: int,
    decline: float = 0.08,
) -> TypeCurve:
    oil, gas, water = [], [], []
    for age in range(periods):
        factor = (1.0 - decline) ** age
        oil.append(oil0 * factor)
        gas.append(gas0 * factor)
        water.append(water0 * factor)
    return TypeCurve(oil=tuple(oil), gas=tuple(gas), water=tuple(water))


def build_operator_scale(
    *,
    n_periods: int = 12,
    n_pads: int = N_PADS,
) -> FieldModel:
    """Build the representative operator-scale inventory.

    Defaults: 20 pads, 12 periods, 5 facility / commercial projects.
    Timing is staggered via earliest_start; each project is go/no-go at that
    epoch (``fix_to_earliest_start``).
    """
    if n_pads < 4:
        raise ValueError("n_pads must be at least 4")

    pad_nodes = tuple(Node(f"pad_{i}", NodeKind.PAD) for i in range(n_pads))
    nodes = pad_nodes + (
        Node("ctb_north", NodeKind.CTB),
        Node("ctb_south", NodeKind.CTB),
        Node("comp", NodeKind.COMPRESSOR),
        Node("plant", NodeKind.PLANT),
        Node("sales", NodeKind.SALES),
        Node("swd", NodeKind.DISPOSAL),
    )

    arcs: list[Arc] = []
    for i in range(n_pads):
        pad = f"pad_{i}"
        ctb = "ctb_north" if i < n_pads // 2 else "ctb_south"
        arcs.extend(
            [
                Arc(f"{pad}_oil", pad, ctb, Commodity.OIL, 2_000.0),
                Arc(f"{pad}_gas", pad, ctb, Commodity.GAS, 2_000.0),
                Arc(f"{pad}_water", pad, ctb, Commodity.WATER, 2_000.0),
            ]
        )

    arcs.extend(
        [
            Arc("north_oil", "ctb_north", "sales", Commodity.OIL, 200.0),
            Arc("south_oil", "ctb_south", "sales", Commodity.OIL, 200.0),
            Arc("north_gas", "ctb_north", "comp", Commodity.GAS, 5_000.0),
            Arc("south_gas", "ctb_south", "comp", Commodity.GAS, 5_000.0),
            Arc("north_water", "ctb_north", "swd", Commodity.WATER, 150.0),
            Arc("south_water", "ctb_south", "swd", Commodity.WATER, 150.0),
            Arc("comp_gas", "comp", "plant", Commodity.GAS, 250.0),
            Arc("plant_gas", "plant", "sales", Commodity.GAS, 250.0),
        ]
    )

    # Stagger pad waves: epochs 0, 3, 6, 9.
    epochs = (0, 3, 6, 9)
    projects: list[Project] = []
    for i in range(n_pads):
        if i < n_pads // 2:
            curve = _decline_curve(oil0=90.0, gas0=100.0, water0=40.0, periods=n_periods)
            capital = (7_500.0,)
        else:
            curve = _decline_curve(oil0=60.0, gas0=160.0, water0=55.0, periods=n_periods)
            capital = (6_500.0,)
        projects.append(
            Project(
                id=f"pad_{i}",
                kind=ProjectKind.DEVELOPMENT,
                capital=capital,
                pad_node=f"pad_{i}",
                type_curve=curve,
                earliest_start=epochs[i % len(epochs)],
            )
        )

    facilities = (
        Project(
            id="comp_expand",
            kind=ProjectKind.FACILITY,
            capital=(18_000.0,),
            earliest_start=0,
            capacity_adds={"comp_gas": 400.0, "plant_gas": 400.0},
        ),
        Project(
            id="north_oil_loop",
            kind=ProjectKind.FACILITY,
            capital=(12_000.0,),
            earliest_start=3,
            capacity_adds={"north_oil": 250.0},
        ),
        Project(
            id="south_oil_loop",
            kind=ProjectKind.FACILITY,
            capital=(12_000.0,),
            earliest_start=3,
            capacity_adds={"south_oil": 250.0},
        ),
        Project(
            id="swd_expand",
            kind=ProjectKind.FACILITY,
            capital=(9_000.0,),
            earliest_start=0,
            capacity_adds={"north_water": 200.0, "south_water": 200.0},
        ),
        Project(
            id="firm_gas_transport",
            kind=ProjectKind.COMMERCIAL,
            capital=(4_000.0, 500.0),
            earliest_start=0,
            lead_time=1,
            capacity_adds={"plant_gas": 150.0, "comp_gas": 150.0},
        ),
    )
    assert len(facilities) == N_FACILITIES
    projects.extend(facilities)

    return FieldModel(
        network=Network(nodes=nodes, arcs=tuple(arcs)),
        projects=tuple(projects),
        n_periods=n_periods,
        prices=Prices(
            oil=72.0,
            gas=3.25,
            water_disposal=1.25,
            discount_rate_per_period=0.008,
        ),
        fix_to_earliest_start=True,
    )
