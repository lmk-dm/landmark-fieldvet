"""Single solver binding: Pyomo + HiGHS.

No silent fallback to another LP/MILP implementation. If HiGHS is unavailable
the call fails closed so a broken seam is visible.
"""

from __future__ import annotations

from typing import Any


def get_highs_solver(*, tee: bool = False, time_limit_sec: float | None = None) -> Any:
    """Return a Pyomo SolverFactory bound to HiGHS via highspy."""
    from pyomo.environ import SolverFactory

    solver = SolverFactory("appsi_highs")
    if solver is None or not solver.available(exception_flag=False):
        # Older Pyomo / missing highspy: try the classic interface once.
        solver = SolverFactory("highs")
    if solver is None or not solver.available(exception_flag=False):
        raise RuntimeError(
            "HiGHS is required for landmark-field-network (install highspy). "
            "No alternate solver is wired."
        )
    if hasattr(solver, "config"):
        try:
            solver.config.stream_solver = tee
        except Exception:
            pass
        if time_limit_sec is not None:
            try:
                solver.config.time_limit = float(time_limit_sec)
            except Exception:
                pass
    if time_limit_sec is not None and hasattr(solver, "highs_options"):
        try:
            opts = dict(getattr(solver, "highs_options", {}) or {})
            opts["time_limit"] = float(time_limit_sec)
            solver.highs_options = opts
        except Exception:
            pass
    return solver
