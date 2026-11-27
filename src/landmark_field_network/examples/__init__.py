"""Built-in Field Network example fields."""

from landmark_field_network.examples.dual_bottleneck import build_dual_bottleneck
from landmark_field_network.examples.mature_water import (
    build_mature_water,
    export_capacity_contract,
    export_for_capital,
)
from landmark_field_network.examples.operator_scale import build_operator_scale
from landmark_field_network.examples.toy_field import build_toy_field
from landmark_field_network.examples.two_pad_tie_in import (
    build_two_pad_tie_in,
    compressor_capex_breakeven,
    enumerate_tie_in_plans,
    preferred_plan,
    tie_in_decision,
)

__all__ = [
    "build_dual_bottleneck",
    "build_mature_water",
    "build_operator_scale",
    "build_toy_field",
    "build_two_pad_tie_in",
    "compressor_capex_breakeven",
    "enumerate_tie_in_plans",
    "export_capacity_contract",
    "export_for_capital",
    "preferred_plan",
    "tie_in_decision",
]
