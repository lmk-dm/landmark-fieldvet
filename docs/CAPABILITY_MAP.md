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
20-pad / 5-facility inventory
  → optimize_portfolio(method=integrated)  # certifies NPV (~2.5s)
  → optimize_portfolio(method=benders)     # same NPV; dual gap open at n=20
  → attribute (standalone/marginal) + economics_project_list handoff
  proof: tests/test_operator_scale.py
Benders formal convergence
  → fix_to_earliest_start inventories through 16 pads
  proof: tests/test_operator_scale.py::test_benders_converges_through_16_pads
network-hydraulics two_pad_gathering
  → shared gas capacity (Mcf/period)
  → enumerate_tie_in_plans / tie_in_decision
  → NPV + timing + compressor breakeven
  → verify_schedule_against_hydraulics
  proof: tests/test_two_pad_tie_in.py
  CLI: fieldvet tie-in
EconomicsHandoff
  → reconcile_plan → landmark_economics.dcf.run_dcf_from_forecast
  proof: tests/test_reconcile.py
  CLI: fieldvet reconcile
NetworkResult shadow prices
  → propose_facility_projects → FieldModel.projects
  proof: tests/test_propose.py
  CLI: fieldvet propose
fixed Plan + Scenario set
  → evaluate_plan_scenarios (E[NPV], CVaR)
  proof: tests/test_scenarios.py
  CLI: fieldvet scenarios
reported_production.csv (public case)
  → validate_fixed_plan
  proof: tests/test_hindcast.py
  CLI: fieldvet hindcast
FieldModel water arcs
  → water_request_from_model → DOE PARETO (optional project-pareto)
  proof: tests/test_pareto.py

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
partial: Benders dual-gap closure at 20 pads; full ARIES deck binary path;
  live PARETO solve_model data tables; volume-DCF reconcile + PARETO adapter active
```
