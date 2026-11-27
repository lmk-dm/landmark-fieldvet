# Capability map — Field Network

```text
CAPABILITY
network_aware_project_selection

OWNER
landmark-field-network

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
network-hydraulics dump_two_pad_capacity / dump_capacity JSON
  → landmark_field_network.hydraulics_capacity (live cargo dump, else frozen JSON)
  → two_pad_tie_in shared gas capacity (Mcf/period)
  → enumerate_tie_in_plans / tie_in_decision
  → NPV + timing + compressor breakeven
  → verify_schedule_against_hydraulics
  proof: tests/test_hydraulics_capacity.py
  proof: tests/test_two_pad_tie_in.py
  CLI: field-network tie-in
  owner of Mcf figures: network-hydraulics (not Field Network)
EconomicsHandoff
  → reconcile_plan → landmark_economics.dcf.run_dcf_from_forecast
  proof: tests/test_reconcile.py
  CLI: field-network reconcile
NetworkResult shadow prices
  → propose_facility_projects → FieldModel.projects
  proof: tests/test_propose.py
  CLI: field-network propose
fixed Plan + Scenario set
  → evaluate_plan_scenarios (E[NPV], CVaR)
  proof: tests/test_scenarios.py
  CLI: field-network scenarios
reported_production.csv (public case)
  → validate_fixed_plan
  proof: tests/test_hindcast.py
  CLI: field-network hindcast
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
  → landmark-field-network owner
  → Plan + AttributionReport
  → landmark-economics / ARIES fiscal reconcile
  → EconomicsHandoff (+ fiscal NPV)
  → landmark-capital AllocationModel (company capital compile)
  → proof: landmark-capital/docs/ESTATE_CAPITAL_PATH.md + validation/coherence_pipeline.py

DELETE AFTER MIGRATION
none yet — no prior Field Network implementation existed

PROOF
pytest in this repo
field-network network|optimize|attribute on toy field

STATUS
MOVED_NOT_WIRED → no: greenfield owner
DUPLICATED meaning with decision-simulation knapsack → NO (different capability)
partial: Benders dual-gap closure at 20 pads; full ARIES deck binary path;
  live PARETO solve_model data tables; volume-DCF reconcile + PARETO adapter active
two_pad capacities: CANONICAL via live dump_capacity (frozen JSON fallback)
```

