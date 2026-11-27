"""Hindcast validation against public-case reported production."""

from __future__ import annotations

from pathlib import Path

from landmark_field_network.examples import build_toy_field
from landmark_field_network.hindcast import load_reported_production_csv, validate_fixed_plan
from landmark_field_network.models import Plan, StartDecision

CASE = Path(__file__).resolve().parents[1] / "cases" / "public_two_pad" / "reported_production.csv"


def test_hindcast_public_case_passes() -> None:
    model = build_toy_field()
    plan = Plan(
        starts=(
            StartDecision("pad_a", 0),
            StartDecision("pad_b", 0),
            StartDecision("comp_expand", 0),
        )
    )
    reported = load_reported_production_csv(CASE)
    report = validate_fixed_plan(model, plan, reported, tol=0.01)
    assert report.passed, report.to_dict()
