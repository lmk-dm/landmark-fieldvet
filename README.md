# landmark-fieldvet

Network-aware selection and timing of upstream projects — pads, facilities,
pipelines, disposal, and commercial commitments — with portfolio value
attributed back to projects.

Standalone NPV ranking assumes project values add. In a capacity-limited field
they do not. FieldVET prices each project through the shared oil / gas / water
network it flows into.

Design: [`docs/FieldVET_Design_v2.md`](docs/FieldVET_Design_v2.md).

## What this owns

| Capability | Status |
|---|---|
| Network flow + curtailment for a fixed plan | **active** (Pyomo + HiGHS) |
| Capacity + forecast duals / debottleneck hints | **active** |
| Selection + timing MILP (small areas) | **active** (`--solver integrated`, default) |
| Benders master ↔ network LP | **active** (`--solver benders`) |
| Standalone / marginal / interaction / Shapley | **active** (exact Shapley for n≤6) |
| Dual-bottleneck parity / scaling probe | **active** |
| 20-pad / 5-facility operator-scale (Benders) | **active** |
| Economics project-list handoff (volumes + timing) | **active** (not fiscal reconcile) |
| ARIES / `landmark-economics` fiscal reconcile | reserved |
| DOE PARETO water reuse | reserved |

## What this does not own

- DCF / fiscal regimes → `landmark-economics` (ARIES is the reported economics path)
- DSU pattern / spacing search → `landmark-dsu`
- Fixed-EV capital/rig knapsack → `landmark-decision-simulation`
- Gathering curtailment on a **given** schedule → `landmark-dsu` fieldopt-plan
- Development UX → `landmark-development`

## Install

```bash
cd 50-decisions-economics/landmark-fieldvet
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Quick proof

```bash
fieldvet network --pads a,b          # curtailment on shared compressor
fieldvet network --pads a,b --expand # expansion clears curtailment
fieldvet optimize                    # integrated MILP (default)
fieldvet optimize --solver benders
fieldvet optimize --case dual --solver benders --pads 4 --periods 12
fieldvet optimize --case operator --solver benders --export /tmp/handoff.json
fieldvet attribute
```

```python
from landmark_fieldvet import Plan, StartDecision, solve_network, optimize_portfolio, attribute
from landmark_fieldvet.examples import build_toy_field

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
landmark-fieldvet

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
  → FieldVET plan
  → landmark-economics / ARIES reconcile
  → capital committee attribution views
```
