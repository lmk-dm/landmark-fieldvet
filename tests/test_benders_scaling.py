"""Scaling probe: largest dual-bottleneck case both solvers certify in time.

Not a unit assertion on a fixed size — records the largest (pads, periods)
pair both solvers solve to matching NPV under a shared time limit.
"""

from __future__ import annotations

import json
from pathlib import Path

from landmark_fieldvet.examples import build_dual_bottleneck
from landmark_fieldvet.master import optimize_portfolio

ABS_TOL = 5.0
REL_TOL = 5e-3
TIME_LIMIT = 30.0
# Small ladder so CI stays fast; expand locally for a fuller curve.
LADDER = (
    (2, 6),
    (3, 8),
    (4, 12),
)


def test_largest_certified_case_under_time_limit(tmp_path: Path) -> None:
    largest = None
    rows = []
    for n_pads, n_periods in LADDER:
        model = build_dual_bottleneck(n_periods=n_periods, n_pads=n_pads)
        try:
            integ = optimize_portfolio(
                model, method="integrated", time_limit_sec=TIME_LIMIT
            )
            bend = optimize_portfolio(
                model,
                method="benders",
                abs_tol=ABS_TOL,
                rel_tol=REL_TOL,
                time_limit_sec=TIME_LIMIT,
            )
        except Exception as exc:  # noqa: BLE001 - scaling probe records failure
            rows.append(
                {
                    "pads": n_pads,
                    "periods": n_periods,
                    "ok": False,
                    "error": str(exc),
                }
            )
            break
        gap = abs(integ.objective - bend.objective)
        ok = gap <= max(ABS_TOL, REL_TOL * max(1.0, abs(integ.objective)))
        row = {
            "pads": n_pads,
            "periods": n_periods,
            "ok": ok,
            "integrated_npv": integ.objective,
            "benders_npv": bend.objective,
            "integrated_runtime_sec": integ.runtime_sec,
            "benders_runtime_sec": bend.runtime_sec,
            "benders_iterations": None if bend.stats is None else bend.stats.iterations,
            "benders_gap": None if bend.stats is None else bend.stats.gap,
            "integrated_plan": [
                {"project": s.project_id, "start": s.start_period}
                for s in integ.plan.starts
            ],
            "benders_plan": [
                {"project": s.project_id, "start": s.start_period}
                for s in bend.plan.starts
            ],
        }
        rows.append(row)
        if not ok or (bend.stats is not None and not bend.stats.converged):
            break
        largest = (n_pads, n_periods)

    report = {
        "time_limit_sec": TIME_LIMIT,
        "abs_tol": ABS_TOL,
        "rel_tol": REL_TOL,
        "largest_certified": None
        if largest is None
        else {"pads": largest[0], "periods": largest[1]},
        "rows": rows,
    }
    out = tmp_path / "benders_scaling.json"
    out.write_text(json.dumps(report, indent=2))
    # Also drop a copy under examples for local inspection when run manually.
    local = Path(__file__).resolve().parents[1] / "examples" / "benders_scaling_last.json"
    local.parent.mkdir(exist_ok=True)
    local.write_text(json.dumps(report, indent=2))

    assert largest is not None, f"no case certified: {report}"
    assert largest[0] >= 2 and largest[1] >= 6
