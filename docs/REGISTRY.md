# Registry entries (workspace mirrors)

Canonical workspace files updated 2026-11-26:

- `portfolio.yaml` → `landmark-fieldvet` status `keep`, zone `50-decisions-economics`
- `LANDMARK_REPOS.md` → table row + narrative owner blurb

## portfolio.yaml (excerpt)

```yaml
landmark-fieldvet:
  status: keep
  recommended_zone: 50-decisions-economics
  notes: >-
    Owns network_aware_project_selection — selection and timing of pads,
    facilities, pipelines, disposal, and commercial commitments with value
    computed through shared oil/gas/water network capacity, plus standalone /
    marginal / interaction / Shapley attribution.
  overlaps_with:
    - landmark-decision-simulation
    - landmark-dsu
    - landmark-development
    - landmark-economics
    - landmark-forecast
```

## Boundary vs overlaps

| Sibling | Sibling owns | FieldVET owns |
|---|---|---|
| `landmark-decision-simulation` | fixed-EV capital/rig knapsack | network-priced selection |
| `landmark-dsu` fieldopt-plan | curtail a fixed schedule | choose projects/timing through the network |
| `landmark-economics` | DCF / fiscal reconcile | linear netbacks inside the optimizer only |
| `landmark-development` | experience / compose | engine capability |
