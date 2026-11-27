"""Minimal CLI for the toy field proof path."""

from __future__ import annotations

import argparse
import json

from landmark_fieldvet.attribution import attribute
from landmark_fieldvet.examples import build_toy_field
from landmark_fieldvet.master import optimize_portfolio
from landmark_fieldvet.models import Plan, StartDecision
from landmark_fieldvet.network import solve_network


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fieldvet", description="FieldVET network-aware portfolio")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_net = sub.add_parser("network", help="Solve network subproblem for a fixed toy plan")
    p_net.add_argument("--pads", default="a,b", help="comma pads: a, b, or a,b")
    p_net.add_argument("--expand", action="store_true", help="include compressor expansion")

    sub.add_parser("optimize", help="Optimize toy field selection and timing")
    sub.add_parser("attribute", help="Optimize toy field then print value attribution")

    args = parser.parse_args(argv)
    model = build_toy_field()

    if args.cmd == "network":
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
            "curtailment": {
                pad: series for pad, series in result.curtailed_fraction.items()
            },
            "shadow_comp_gas": result.shadow_price.get("comp_gas", []),
            "projects": [s.project_id for s in starts],
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.cmd == "optimize":
        opt = optimize_portfolio(model)
        payload = {
            "objective": opt.objective,
            "plan": [
                {"project": s.project_id, "start": s.start_period} for s in opt.plan.starts
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.cmd == "attribute":
        opt = optimize_portfolio(model)
        report = attribute(model, opt.plan, portfolio_result=opt.network, shapley_samples=24)
        payload = {
            "plan": [
                {"project": s.project_id, "start": s.start_period} for s in opt.plan.starts
            ],
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
