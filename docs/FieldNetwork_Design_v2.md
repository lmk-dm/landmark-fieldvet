# Field Network: Network-Aware Project Selection for Upstream Development

Design specification, draft 2 — Kyle Jones, November 2026

## Purpose

Every operator ranks development projects by standalone NPV or profitability index and funds down the list until capital runs out. That method assumes value is additive. In an unconventional field it is not. A pad's value depends on whether the compressor station it flows to gets expanded. A compressor expansion's value depends on how many pads are brought online behind it. Two pads that share a gathering line compete for its capacity, so funding both is worth less than the sum of funding each. A firm transport contract is worth nothing without the wells to fill it and a great deal with them.

Field Network selects and times a portfolio of upstream projects (pads, facilities, pipelines, disposal, and commercial commitments) by computing each project's value through the shared network it flows into, not in isolation. It then reports what each project contributes to the portfolio, attributed so the contributions sum exactly to portfolio NPV. That attribution is the part no current tool provides, and it is the part a capital committee needs.

## What carries over from DER-VET

DER-VET's central idea is that resources sharing a constraint must be valued together. A battery cannot sell energy arbitrage and hold spinning reserve with the same megawatt in the same hour, so DER-VET co-optimizes the mix of resources and the services they provide rather than summing each one's value. Field Network applies the same idea to projects that share network capacity. The shared constraint is pipe, compression, processing, and disposal capacity over time instead of a battery's megawatts in an hour.

Three DER-VET choices carry over directly. The tool optimizes the mix, not individual items. It decomposes total value into its sources so the answer can be explained. And it publishes its formulation and data so the answer can be trusted by parties with conflicting interests.

## The network effects that matter

Five interactions make upstream project value non-additive. Each one is routinely missed by standalone economics.

**Capacity complements.** Facility and pipeline projects have no value without production to fill them, and pads have reduced value without capacity to flow into. The pad and the compressor are worth more together than apart.

**Capacity substitutes.** Pads and wells that flow into the same constrained arc cannibalize each other. A new pad brought online into a full system curtails existing wells. Its standalone NPV counts its own barrels and ignores the barrels it displaces.

**Commercial commitments.** Minimum volume commitments and take-or-pay contracts create a penalty when unfilled. That penalty makes the marginal pad behind a commitment more valuable than its standalone economics show, and makes a new commitment risky unless the inventory to fill it is funded.

**Subsurface interference.** Parent-child depletion and offset frac hits make a pad's production depend on whether and when its neighbors are developed. Co-developing a section as a cube produces a different profile from developing it in stages.

**Shared fixed cost.** Roads, power, central facilities, and water infrastructure serve many pads. Their cost is incurred once and benefits every project behind them, which standalone economics either ignores or allocates by an arbitrary rule.

## What exists today

Two categories of commercial tool address parts of this problem, and the gap sits between them.

**Portfolio optimizers.** Quorum's Planning Space Portfolio and SLB's Merak Capital Planning choose the selection and timing of opportunities to maximize value under budget, production, and other constraints, with dependencies between projects. As publicly described, each opportunity carries its own pre-computed production and cash flow profile, and dependencies are logical: one project requires another, two are mutually exclusive. Value does not come from routing flows through a capacity network, so cannibalization and fill effects are not computed. The optimizer is solving a constrained knapsack over fixed values.

**Development planning simulators.** Quorum's Enersight models the network directly: takeaway limits, facility curtailment, water handling, flow splitting across sales points, inter-well effects, and drill-to-fill scheduling. It is the strongest existing tool on network fidelity. As publicly described, its schedules are built from planner inputs, priorities, and sequencing rules, and alternatives are compared as scenarios. It simulates the network consequences of a plan very well. It does not search over the space of portfolios to find the one that maximizes network-coupled value, and it does not attribute portfolio value back to individual projects.

The open gap is to optimize over selection and timing with value computed through the network, and to attribute the result. Quorum owns both halves of the existing capability, which makes it the most likely competitor to close the gap and the main reason to move first.

## Formulation

Field Network is a mixed-integer linear program with a natural decomposition.

### Projects and decisions

Each candidate project *j* has a type, a capital profile, an earliest start, a lead time, and the network change it creates. Development projects (a pad or drilling spacing unit, with variants such as staged or cube co-development) add production at a node. Facility projects (a compressor station expansion, a central tank battery, a gathering line loop, a saltwater disposal well, a recycle plant) add capacity to arcs or nodes. Commercial projects (a firm transport contract, a processing agreement, a minimum volume commitment) add capacity at a sales point together with a fee structure and a shortfall penalty.

The decision variable is binary: *x(j,τ)* equals one if project *j* starts in period *τ*, and each project starts at most once. Production from a development project follows its type curve shifted to its start date. Because the type curve is a known profile, the shift is linear: forecast production in period *t* is the sum over *τ* of *x(j,τ)* times the type curve at age *t − τ*. This keeps the whole model linear without approximating the timing decision.

### Network

The field is a directed graph of pads, central tank batteries, compressor stations, processing plants, sales points, and disposal sites, carried for three commodities: oil, gas, and water. Each arc has a base capacity plus the capacity added by facility and commercial projects once they are online. Flows in each period must balance at every node and respect arc capacity.

Production at each pad is the forecast minus curtailment. Curtailment is a single fraction applied to all three phases at the pad, which preserves the pad's gas-oil and water-oil ratios and keeps the coupling linear. When gas capacity binds, oil is curtailed with it. That coupling is where most of the network value lives.

### Interference and variants

Subsurface interference is handled through project variants rather than pairwise nonlinear terms. A section can be developed as a single cube project or as staged parent and child projects, each with its own type curves derived from the reservoir team's spacing and timing studies. Mutual exclusion between variants lets the optimizer choose the development style. Where staged development is chosen, a precedence constraint and a degraded child type curve represent the parent's depletion.

### Constraints

Beyond the network, the model enforces rig and frac crew counts per period, annual capital budgets, precedence and exclusion between projects, minimum volume commitments with shortfall penalties, production or cash flow targets where the plan requires them, and permit limits on flaring and disposal.

### Objective

Maximize expected portfolio NPV over price and type-curve scenarios. A risk-adjusted variant maximizes expected NPV minus a weight on conditional value at risk, which lets management trade value for downside protection explicitly. Cash flows use linear netbacks for revenue, royalty, and severance, fixed and variable operating cost, and project capital. The final selected plan is then run through ARIES for a full fiscal reconciliation, so the optimizer's linear economics never become the reported numbers.

### Decomposition

The model splits cleanly into a master problem and subproblems, which is what makes it tractable at field scale. The master problem chooses selection and timing (all the binaries). For a fixed plan, each scenario's subproblem is a linear network flow problem that computes production, curtailment, and cash flow. The subproblem's dual values (the shadow prices on arc capacity in each period) return to the master problem as Benders cuts that tell it how much each unit of capacity is worth under the current plan.

Those same shadow prices drive two outputs. They identify where debottlenecking pays, which generates new facility project candidates automatically: wherever the shadow price on an arc, summed over time, exceeds the cost of expanding it. And they feed the value attribution below.

Planning periods are monthly for the first three years and quarterly after, which reflects both forecast precision and when decisions can still change.

## Value attribution

The primary output is not the optimal plan. It is an explanation of why the plan is worth what it is worth, in four views.

**Standalone value.** Each project evaluated alone against the existing network. This is what operators compute today, kept as the reference point.

**Marginal value in the plan.** Portfolio NPV with the project minus portfolio NPV without it, re-optimizing the rest. This is the true value of funding the project given everything else in the plan, and it differs from standalone value whenever network effects bind.

**Interaction values.** For pairs of projects that share an arc, the value of funding both minus the value of funding each alone. A positive interaction marks complements, such as a pad and the compressor behind it. A negative interaction marks substitutes, such as two pads competing for one gathering line. The interaction matrix shows a capital committee which projects must be approved or rejected together.

**Attributed value.** Portfolio NPV allocated across projects by Shapley value, which averages each project's marginal contribution over many orderings in which the portfolio could be assembled. Shapley allocation is the only standard method whose shares sum exactly to the total while treating projects symmetrically. Exact computation is infeasible for hundreds of projects, so Field Network estimates it by sampling orderings and solving each through the network subproblem, using the shadow prices to approximate the marginal contribution of facility projects cheaply.

Attributed value replaces the ranked list. It answers the question an asset team actually brings to a capital meeting: what is this project worth to the company, given the rest of what we are funding?

## Architecture

The core is a Python package built on Pyomo, chosen for its mature support for decomposition and for compatibility with DOE's open-source PARETO produced water optimizer, whose water network model Field Network can reuse rather than rebuild. HiGHS is the default solver, with Gurobi optional for large portfolios.

Inputs are a project inventory with type curves and capital profiles, the network graph with base capacities, price and type-curve scenarios, resource availability, budgets, and commercial terms. These come from existing systems: type curves and economics parameters from ARIES, well and pad inventory from the development planning system, and the network from facilities engineering. Outputs are the selected plan with timing, monthly network flows and curtailment, the four value views, the shadow price map, and generated debottlenecking candidates, exported as Parquet and as an ARIES-compatible project list.

## Validation

Validation runs in three steps. First, with the plan fixed to an operator's actual development schedule, Field Network's network subproblem must reproduce the operator's reported production and curtailment within an agreed tolerance. This proves the network model before the optimizer is trusted. Second, the optimized plan's linear economics must reconcile with a full ARIES run of the same plan. Third, a hindcast: reconstruct a Delaware Basin development area from public Texas Railroad Commission permit, completion, and production data, run Field Network with only the information available at a past decision date, and compare its plan and attributed values with what the operator built and how it performed.

## Open questions

Which type-curve variants for staged versus cube development can the reservoir team supply with enough confidence to drive the optimizer? Does Planning Space Portfolio support shared capacity constraints beyond aggregate caps, which would narrow the gap described above? How large a portfolio, in candidate projects and planning periods, must version 1 solve for a representative operator? Will asset teams accept Shapley attribution in place of standalone ranking, or does it need to appear alongside standalone values for several planning cycles first? Which operator would serve as a design partner with a real inventory and network?

## Next actions

Build the network subproblem first and validate it against one operator's actual schedule, because every downstream output depends on it. Add the master problem with selection and timing for a 20-pad, 5-facility area and confirm the Benders loop converges. Implement marginal, interaction, and sampled Shapley values on that case and review them with an asset team against their current ranking. Decide the open-core boundary, and whether ARIES integration is the commercial wedge, before publishing any code.
