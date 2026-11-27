"""PARETO water adapter."""

from __future__ import annotations

import pytest

from landmark_fieldvet.examples import build_toy_field
from landmark_fieldvet.pareto import available, solve_strategic_water, water_request_from_model


def test_water_request_extracts_disposal() -> None:
    model = build_toy_field()
    req = water_request_from_model(model, case_id="toy_water")
    assert "swd" in req.disposal_nodes
    assert req.disposal_capacity.get("swd", 0.0) > 0.0
    assert "pad_a" in req.produced_water_forecast


def test_solve_without_pareto_fails_closed() -> None:
    if available():
        pytest.skip("project-pareto installed in this environment")
    model = build_toy_field()
    req = water_request_from_model(model)
    with pytest.raises(ImportError, match="project-pareto"):
        solve_strategic_water(req)
