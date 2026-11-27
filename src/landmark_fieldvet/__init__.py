"""FieldVET: network-aware upstream project selection and value attribution."""

from landmark_fieldvet.attribution import AttributionReport, attribute
from landmark_fieldvet.benders import BendersResult, BendersStats, optimize_benders
from landmark_fieldvet.export import EconomicsHandoff, ExportedProject, economics_project_list
from landmark_fieldvet.hindcast import HindcastReport, load_reported_production_csv, validate_fixed_plan
from landmark_fieldvet.master import OptimizeResult, optimize_portfolio
from landmark_fieldvet.models import (
    Arc,
    Commodity,
    FieldModel,
    Network,
    Node,
    NodeKind,
    Plan,
    Prices,
    Project,
    ProjectKind,
    StartDecision,
    TypeCurve,
)
from landmark_fieldvet.network import NetworkResult, debottleneck_candidates, solve_network
from landmark_fieldvet.pareto import ParetoWaterRequest, water_request_from_model
from landmark_fieldvet.plan_effects import PlanEffects, apply_plan
from landmark_fieldvet.propose import propose_facility_projects, with_proposed_facilities
from landmark_fieldvet.reconcile import FiscalReconcileReport, reconcile_plan
from landmark_fieldvet.scenarios import Scenario, ScenarioEvaluation, evaluate_plan_scenarios

__all__ = [
    "EconomicsHandoff",
    "ExportedProject",
    "FiscalReconcileReport",
    "HindcastReport",
    "ParetoWaterRequest",
    "Arc",
    "AttributionReport",
    "BendersResult",
    "BendersStats",
    "Commodity",
    "FieldModel",
    "Network",
    "NetworkResult",
    "Node",
    "NodeKind",
    "OptimizeResult",
    "Plan",
    "PlanEffects",
    "Prices",
    "Project",
    "ProjectKind",
    "Scenario",
    "ScenarioEvaluation",
    "StartDecision",
    "TypeCurve",
    "apply_plan",
    "attribute",
    "debottleneck_candidates",
    "economics_project_list",
    "evaluate_plan_scenarios",
    "load_reported_production_csv",
    "optimize_benders",
    "optimize_portfolio",
    "propose_facility_projects",
    "reconcile_plan",
    "solve_network",
    "validate_fixed_plan",
    "water_request_from_model",
    "with_proposed_facilities",
]

__version__ = "0.1.0"
