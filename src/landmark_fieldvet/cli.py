"""Minimal CLI for FieldVET proofs."""

from __future__ import annotations

import argparse
import json

from landmark_fieldvet.attribution import attribute
from landmark_fieldvet.examples import build_dual_bottleneck, build_toy_field
from landmark_fieldvet.master import optimize_portfolio
from landmark_fieldvet.models import Plan, StartDecision
from landmark_fieldvet.network import solve_network


def _plan_payload(opt) -> dict:
    payload = {
        "solver": opt.solver,
        "objective": opt.objective,
        "runtime_sec": opt.runtime_sec,
        "plan": [
            {"project": s.project_id, "start": s.start_period} for s in opt.plan.starts
        ],
        "curtailment": {
            pad: series for pad, series in opt.network.curtailed_fraction.items()
        },
    }
    if opt.stats is not None:
        payload["benders"] = {
            "iterations": opt.stats.iterations,
            "cuts": opt.stats.cuts,
            "lower_bound": opt.stats.lower_bound,
            "upper_bound": opt.stats.upper_bound,
            "gap": opt.stats.gap,
            "converged": opt.stats.converged,
        }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fieldvet", description="FieldVET network-aware portfolio")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_net = sub.add_parser("network", help="Solve network subproblem for a fixed toy plan")
    p_net.add_argument("--pads", default="a,b", help="comma pads: a, b, or a,b")
    p_net.add_argument("--expand", action="store_true", help="include compressor expansion")

    p_opt = sub.add_parser("optimize", help="Optimize a field model")
    p_opt.add_argument(
        "--solver",
        choices=("integrated", "benders"),
        default="integrated",
        help="integrated MILP (default) or Benders",
    )
    p_opt.add_argument(
        "--case",
        choices=("toy", "dual"),
        default="toy",
        help="toy two-pad field or dual-bottleneck benchmark",
    )
    p_opt.add_argument("--pads", type=int, default=4, help="pad count for dual case")
    p_opt.add_argument("--periods", type=int, default=12, help="periods for dual case")
    p_opt.add_argument("--time-limit", type=float, default=120.0)

    p_attr = sub.add_parser("attribute", help="Optimize toy field then print value attribution")
    p_attr.add_argument(
        "--solver",
        choices=("integrated", "benders"),
        default="integrated",
    )

    args = parser.parse_args(argv)

    if args.cmd == "network":
        model = build_toy_field()
        starts: list[StartDecision] = []
        pads = {p.strip().lower() for p in args.pads.split(",") if p.strip()}
        if "a" in pads:
            starts.append(StartDecision("pad_a", 0))
        if "b" in pads:
            starts.append(StartDecision("pad_b", 0))
        if args.expand:
            starts.append(StartDecision("comp_expand", 0))
        result = solve_network(model, Plan(starts=tuple(starts)))
        payload = {
            "objective": result.objective,
            "operating_npv": result.operating_npv,
            "curtailment": {
                pad: series for pad, series in result.curtailed_fraction.items()
            },
            "shadow_comp_gas": result.shadow_price.get("comp_gas", []),
            "projects": [s.project_id for s in starts],
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.cmd == "optimize":
        if args.case == "toy":
            model = build_toy_field()
        else:
            model = build_dual_bottleneck(n_periods=args.periods, n_pads=args.pads)
        opt = optimize_portfolio(
            model,
            method=args.solver,
            time_limit_sec=args.time_limit,
        )
        print(json.dumps(_plan_payload(opt), indent=2))
        return 0

    if args.cmd == "attribute":
        model = build_toy_field()
        opt = optimize_portfolio(model, method=args.solver)
        report = attribute(model, opt.plan, portfolio_result=opt.network, shapley_samples=24)
        payload = {
            **_plan_payload(opt),
            "portfolio_npv": report.portfolio_npv,
            "standalone": report.standalone,
            "marginal": report.marginal,
            "interaction": {f"{a}|{b}": v for (a, b), v in report.interaction.items()},
            "shapley": report.shapley,
        }
        print(json.dumps(payload, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
