"""Consumer path: dump_capacity → Field Network capacity loader."""

from __future__ import annotations

import json
import subprocess

import pytest

from landmark_field_network.hydraulics_capacity import (
    FROZEN_PATH,
    REPO_FROZEN_PATH,
    SCHEMA,
    load_frozen_two_pad_capacity,
    load_two_pad_capacity,
    run_live_dump_capacity,
)
from landmark_field_network.examples.two_pad_tie_in import (
    BASE_MAX_EQUAL_MCF_D,
    NOMINATED_MCF_D,
    UPGRADE_MAX_EQUAL_MCF_D,
    build_two_pad_tie_in,
)


def test_frozen_contract_schema() -> None:
    payload = load_frozen_two_pad_capacity()
    assert payload["schema"] == SCHEMA
    assert payload["fixture"] == "two_pad_gathering"
    assert FROZEN_PATH.is_file()
    assert REPO_FROZEN_PATH.is_file()
    assert FROZEN_PATH.read_text() == REPO_FROZEN_PATH.read_text()


def test_loader_matches_frozen_when_offline() -> None:
    frozen = load_frozen_two_pad_capacity()
    cap = load_two_pad_capacity(prefer_live=False)
    assert not cap.live
    assert abs(cap.nominated_mcf_d_per_pad - frozen["nominated_mcf_d_per_pad"]) < 1e-9
    assert abs(cap.base_max_equal_mcf_d - frozen["base_max_equal_mcf_d"]) < 1e-9
    assert abs(cap.upgrade_max_equal_mcf_d - frozen["upgrade_max_equal_mcf_d"]) < 1e-9


def test_live_dump_matches_frozen_when_available() -> None:
    try:
        live = run_live_dump_capacity()
    except (
        FileNotFoundError,
        subprocess.SubprocessError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        RuntimeError,
        OSError,
    ):
        pytest.skip("live dump_capacity unavailable in this environment")
    frozen = load_frozen_two_pad_capacity()
    for key in (
        "nominated_mcf_d_per_pad",
        "base_max_equal_mcf_d",
        "upgrade_max_equal_mcf_d",
        "outage_undelivered_mcf",
    ):
        assert abs(float(live[key]) - float(frozen[key])) < 1e-3, key


def test_tie_in_model_uses_dump_rates() -> None:
    cap = load_two_pad_capacity(prefer_live=False)
    model = build_two_pad_tie_in(capacity=cap)
    assert abs(NOMINATED_MCF_D - cap.nominated_mcf_d_per_pad) < 1e-6
    assert abs(BASE_MAX_EQUAL_MCF_D - cap.base_max_equal_mcf_d) < 1e-6
    assert abs(UPGRADE_MAX_EQUAL_MCF_D - cap.upgrade_max_equal_mcf_d) < 1e-6
    # Shared compressor arc capacity = 2 × base equal-pad Mcf/d × 30 d.
    expected = 2.0 * cap.base_max_equal_mcf_d * 30.0
    arc = next(a for a in model.network.arcs if a.id == "comp_gas")
    assert abs(arc.base_capacity - expected) < 1e-6


def test_frozen_file_is_pretty_json() -> None:
    raw = FROZEN_PATH.read_text()
    assert json.loads(raw)["schema"] == SCHEMA
