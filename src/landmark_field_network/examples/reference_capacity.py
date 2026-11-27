"""Published spare-capacity contracts for Reference Energy assets.

Each contract is the base trunk capacity on a field-network model for that
asset. Facility Candidates in landmark-capital still carry gas_add / water_add;
do not inflate spare by those adds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Base trunk capacities (synthetic). Tuned so one expansion unit is material
# relative to producer reservations without inventing a fraction of demand.
CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "asset": "Permian",
        "country": "US",
        "state": "TX",
        "admin1_key": "US-TX",
        "spare_gas_mscfd": 100_000.0,
        "spare_water_bwpd": 80_000.0,
        "source": "landmark-field-network.examples.reference_capacity",
        "limiting_arc": "comp_gas + water_disposal",
    },
    {
        "asset": "Eagle Ford",
        "country": "US",
        "state": "TX",
        "admin1_key": "US-TX",
        "spare_gas_mscfd": 50_000.0,
        "spare_water_bwpd": 40_000.0,
        "source": "landmark-field-network.examples.reference_capacity",
        "limiting_arc": "comp_gas + water_disposal",
    },
    {
        "asset": "Bakken",
        "country": "US",
        "state": "ND",
        "admin1_key": "US-ND",
        "spare_gas_mscfd": 60_000.0,
        "spare_water_bwpd": 30_000.0,
        "source": "landmark-field-network.examples.reference_capacity",
        "limiting_arc": "comp_gas + gas_capture trunk",
    },
    {
        "asset": "Gulf of Mexico",
        "country": "US",
        "state": "",
        "admin1_key": "US",
        "spare_gas_mscfd": 25_000.0,
        "spare_water_bwpd": 15_000.0,
        "source": "landmark-field-network.examples.reference_capacity",
        "limiting_arc": "offshore compression trunk",
    },
    {
        "asset": "Mature conventional",
        "country": "US",
        "state": "TX",
        "admin1_key": "US-TX",
        "spare_gas_mscfd": 0.0,
        "spare_water_bwpd": 20_000.0,
        "source": "landmark-field-network.examples.mature_water",
        "limiting_arc": "inject_water",
    },
)


def contracts() -> list[dict[str, Any]]:
    out = []
    for row in CONTRACTS:
        item = dict(row)
        item["synthetic"] = True
        item["notes"] = (
            "Base spare capacity from the field-network capacity contract. "
            "Facility Candidates add capacity via gas_add_mscfd / water_add_bwpd."
        )
        out.append(item)
    return out


def write_contracts(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for row in contracts():
        slug = (
            row["asset"]
            .lower()
            .replace(" ", "_")
            .replace("of_", "")
        )
        # gulf_mexico, mature_conventional, …
        if row["asset"] == "Gulf of Mexico":
            slug = "gulf_of_mexico"
        path = out_dir / f"{slug}_capacity.json"
        path.write_text(json.dumps(row, indent=2) + "\n")
        paths.append(path)
    return paths


__all__ = ["CONTRACTS", "contracts", "write_contracts"]
