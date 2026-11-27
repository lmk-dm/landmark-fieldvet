"""Load two-pad gas capacities from network-hydraulics ``dump_capacity``.

Canonical owner: ``network-hydraulics`` (``dump_two_pad_capacity``).
Field Network adapts the JSON contract into Mcf/period arc capacities; it does
not recompute dry-gas hydraulics.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "network-hydraulics.two_pad_capacity.v1"
_MODULE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _MODULE_DIR.parents[1]  # .../landmark-field-network
FROZEN_PATH = _MODULE_DIR / "data" / "two_pad_capacity.json"
# Repo-level mirror kept for humans / estate docs (same bytes as FROZEN_PATH).
REPO_FROZEN_PATH = _REPO_ROOT / "data" / "two_pad_capacity.json"
_DEFAULT_NETWORK_CORE = (
    _REPO_ROOT.parent.parent / "80-oil-pipelines" / "landmark-network-core"
)


@dataclass(frozen=True)
class TwoPadCapacity:
    """Field-facing view of the hydraulics dump contract."""

    nominated_mcf_d_per_pad: float
    base_max_equal_mcf_d: float
    upgrade_max_equal_mcf_d: float
    outage_undelivered_mcf: float
    pad_rate_kg_s: float
    outage_duration_hours: float
    source: str
    live: bool

    @property
    def base_shared_gas_mcf_d(self) -> float:
        return 2.0 * self.base_max_equal_mcf_d

    @property
    def upgrade_shared_gas_mcf_d(self) -> float:
        return 2.0 * self.upgrade_max_equal_mcf_d


def _network_core_root() -> Path:
    env = os.environ.get("LANDMARK_NETWORK_CORE_ROOT")
    if env:
        return Path(env)
    return _DEFAULT_NETWORK_CORE


def _validate(payload: dict) -> dict:
    if payload.get("schema") != SCHEMA:
        raise ValueError(
            f"unexpected capacity schema {payload.get('schema')!r}; want {SCHEMA}"
        )
    for key in (
        "nominated_mcf_d_per_pad",
        "base_max_equal_mcf_d",
        "upgrade_max_equal_mcf_d",
        "outage_undelivered_mcf",
        "pad_rate_kg_s",
        "outage_duration_hours",
        "source",
    ):
        if key not in payload:
            raise ValueError(f"capacity dump missing {key}")
    return payload


def load_frozen_two_pad_capacity(path: Path | None = None) -> dict:
    """Checked-in dump JSON (offline / CI without a Rust toolchain path)."""
    target = path or FROZEN_PATH
    return _validate(json.loads(target.read_text()))


def run_live_dump_capacity(
    *,
    network_core: Path | None = None,
    outage_hours: float = 48.0,
) -> dict:
    """Invoke ``cargo run -p network-hydraulics --example dump_capacity``."""
    if outage_hours != 48.0:
        raise ValueError("live dump_capacity example is fixed at 48 h outage")
    root = network_core or _network_core_root()
    manifest = root / "Cargo.toml"
    if not manifest.is_file():
        raise FileNotFoundError(f"network-core workspace not found at {manifest}")
    cargo = shutil.which("cargo")
    if cargo is None:
        raise FileNotFoundError("cargo not on PATH")
    proc = subprocess.run(
        [
            cargo,
            "run",
            "-p",
            "network-hydraulics",
            "--example",
            "dump_capacity",
            "--release",
            "--quiet",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    # cargo may still print compile lines on stderr; stdout is JSON only.
    text = proc.stdout.strip()
    start = text.find("{")
    if start < 0:
        raise RuntimeError(f"dump_capacity produced no JSON: {text!r}")
    return _validate(json.loads(text[start:]))


def load_two_pad_capacity(*, prefer_live: bool | None = None) -> TwoPadCapacity:
    """Prefer a live dump when available; otherwise the frozen contract file."""
    if prefer_live is None:
        prefer_live = os.environ.get("LMK_LIVE_DUMP_CAPACITY", "1") not in (
            "0",
            "false",
            "False",
        )
    live = False
    if prefer_live:
        try:
            payload = run_live_dump_capacity()
            live = True
        except (FileNotFoundError, subprocess.SubprocessError, TimeoutError, ValueError, json.JSONDecodeError):
            payload = load_frozen_two_pad_capacity()
    else:
        payload = load_frozen_two_pad_capacity()
    return TwoPadCapacity(
        nominated_mcf_d_per_pad=float(payload["nominated_mcf_d_per_pad"]),
        base_max_equal_mcf_d=float(payload["base_max_equal_mcf_d"]),
        upgrade_max_equal_mcf_d=float(payload["upgrade_max_equal_mcf_d"]),
        outage_undelivered_mcf=float(payload["outage_undelivered_mcf"]),
        pad_rate_kg_s=float(payload["pad_rate_kg_s"]),
        outage_duration_hours=float(payload["outage_duration_hours"]),
        source=str(payload["source"]),
        live=live,
    )
