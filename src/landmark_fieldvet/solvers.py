"""Single solver binding: Pyomo + HiGHS.

No silent fallback to another LP/MILP implementation. If HiGHS is unavailable
the call fails closed so a broken seam is visible.
"""

from __future__ import annotations

from typing import Any


def get_highs_solver(*, tee: bool = False) -> Any:
    """Return a Pyomo SolverFactory bound to HiGHS via highspy."""
    from pyomo.environ import SolverFactory

    solver = SolverFactory("appsi_highs")
    if solver is None or not solver.available(exception_flag=False):
        # Older Pyomo / missing highspy: try the classic interface once.
        solver = SolverFactory("highs")
    if solver is None or not solver.available(exception_flag=False):
        raise RuntimeError(
            "HiGHS is required for landmark-fieldvet (install highspy). "
            "No alternate solver is wired."
        )
    if hasattr(solver, "config"):
        try:
            solver.config.stream_solver = tee
        except Exception:
            pass
    return solver
