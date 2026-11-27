# landmark-field-network

Network-aware selection and timing of upstream projects — pads, facilities,
pipelines, disposal, and commercial commitments — with portfolio value
attributed back to projects.

Standalone NPV ranking assumes project values add. In a capacity-limited field
they do not. Field Network prices each project through the shared oil / gas / water
network it flows into.

Design: [`docs/FieldNetwork_Design_v2.md`](docs/FieldNetwork_Design_v2.md).

## What this owns

| Capability | Status |
|---|---|
| Network flow + curtailment for a fixed plan | **active** (Pyomo + HiGHS) |
| Capacity + forecast duals / debottleneck hints | **active** |
| Selection + timing MILP (small areas) | **active** (`--solver integrated`, default) |
| Benders master ↔ network LP | **active** (`--solver benders`) |
| Standalone / marginal / interaction / Shapley | **active** (exact Shapley for n≤6) |
| Dual-bottleneck parity / scaling probe | **active** |
| 20-pad / 5-facility operator-scale | **active** (integrated certifies NPV; Benders matches) |
| Benders formal gap closure | **active** through 16 pads; open at 20 |
| Economics project-list handoff (volumes + timing) | **active** |
| ARIES / `landmark-economics` fiscal reconcile | **active** (volume DCF via `reconcile_plan`) |
| Auto-propose facilities from shadow prices | **active** (`propose_facility_projects`) |
| Price scenarios + CVaR | **active** (`evaluate_plan_scenarios`) |
| Hindcast vs reported production CSV | **active** (public two-pad case) |
| DOE PARETO water reuse | **adapter** (`water_request_from_model`; solve needs `project-pareto`) |
| Open public case | **active** (`cases/public_two_pad`, Apache-2.0) |

## What this does not own

- DCF kernel itself → `landmark-economics` (Field Network calls it for reconcile; does not reimplement)
- Company capital allocation across assets → `landmark-capital` (consumes `EconomicsHandoff` as Candidates; see `landmark-capital/docs/ESTATE_CAPITAL_PATH.md`)
- DSU pattern / spacing search → `landmark-dsu`
- Fixed-EV capital/rig knapsack → `landmark-decision-simulation`
- Gathering curtailment on a **given** schedule → `landmark-dsu` fieldopt-plan
- Development UX → `landmark-development`

## Install

```bash
cd 50-decisions-economics/landmark-field-network
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Quick proof

```bash
field-network network --pads a,b          # curtailment on shared compressor
field-network network --pads a,b --expand # expansion clears curtailment
field-network optimize                    # integrated MILP (default)
field-network optimize --solver benders
field-network optimize --case dual --solver benders --pads 4 --periods 12
field-network optimize --case operator --solver benders --export /tmp/handoff.json
field-network attribute
field-network tie-in                      # hydraulic capacities → which / when / compressor
field-network reconcile                   # landmark-economics fiscal NPV on the plan
field-network propose                     # auto facility projects from shadow prices
field-network scenarios                   # price scenarios + CVaR
field-network hindcast                   # validate vs cases/public_two_pad CSV
```

```python
from landmark_field_network import Plan, StartDecision, solve_network, optimize_portfolio, attribute
from landmark_field_network.examples import build_toy_field

model = build_toy_field()
result = solve_network(model, Plan(starts=(StartDecision("pad_a", 0), StartDecision("pad_b", 0))))
opt = optimize_portfolio(model)
report = attribute(model, opt.plan, portfolio_result=opt.network)
```

## Estate seam

```text
CAPABILITY
network_aware_project_selection

OWNER
landmark-field-network

ACTIVE PATHS
toy / operator inventory
  → FieldModel + Plan
  → solve_network (LP) | optimize_portfolio (MILP)
  → NetworkResult + AttributionReport

DUPLICATE PATHS (not this owner)
landmark-decision-simulation mixed_integer  → fixed EV knapsack
landmark-dsu fieldopt-plan Capacity         → curtail fixed schedule
landmark-development POST /portfolio        → screening / experience

TARGET PATH
inventory + network + prices
  → Field Network plan
  → landmark-economics / ARIES reconcile
  → capital committee attribution views
```
