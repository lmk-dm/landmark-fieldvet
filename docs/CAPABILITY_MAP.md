# Capability map — FieldVET

```text
CAPABILITY
network_aware_project_selection

OWNER
landmark-fieldvet

ACTIVE PATHS
fixed Plan
  → apply_plan (forecast + capacity)
  → solve_network (Pyomo LP, HiGHS)
  → produced / curtailment / shadow_price
  proof: tests/test_network_curtailment.py
  proof: tests/test_shadow_prices.py
FieldModel inventory
  → optimize_portfolio(method=integrated)  # default reference
  → Plan + re-solved network duals
  proof: tests/test_selection_timing.py
FieldModel inventory
  → optimize_portfolio(method=benders)
  → master binaries + network LP cuts
  → same Plan / NetworkResult contracts
  proof: tests/test_benders_parity.py
  proof: tests/test_benders_scaling.py
Plan
  → attribute (standalone, marginal, interaction, Shapley)
  proof: tests/test_attribution.py

DUPLICATE PATHS
landmark-decision-simulation evaluation/portfolio.py
  → binary knapsack over fixed Alternative EV
  → capital / rig / people caps only
landmark-dsu fieldopt-plan constraints Capacity
  → curtail volumes on a fixed development schedule
  → does not choose projects
landmark-development POST /api/v1/portfolio
  → screening / experience compose
field-architect
  → explicit non-goal: not a facilities network optimizer

TARGET PATH
consumer (development / capital planning)
  → FieldModel contract
  → landmark-fieldvet owner
  → Plan + AttributionReport
  → landmark-economics / ARIES fiscal reconcile

DELETE AFTER MIGRATION
none yet — no prior FieldVET implementation existed

PROOF
pytest in this repo
fieldvet network|optimize|attribute on toy field

STATUS
MOVED_NOT_WIRED → no: greenfield owner
DUPLICATED meaning with decision-simulation knapsack → NO (different capability)
partial: ARIES reconcile, PARETO water bind, operator-scale fixture still open
```
