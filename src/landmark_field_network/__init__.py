"""Field Network: network-aware upstream project selection and value attribution."""

from landmark_field_network.attribution import AttributionReport, attribute
from landmark_field_network.benders import BendersResult, BendersStats, optimize_benders
from landmark_field_network.export import EconomicsHandoff, ExportedProject, economics_project_list
from landmark_field_network.hindcast import HindcastReport, load_reported_production_csv, validate_fixed_plan
from landmark_field_network.master import OptimizeResult, optimize_portfolio
from landmark_field_network.models import (
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
from landmark_field_network.network import NetworkResult, debottleneck_candidates, solve_network
from landmark_field_network.pareto import ParetoWaterRequest, water_request_from_model
from landmark_field_network.plan_effects import PlanEffects, apply_plan
from landmark_field_network.propose import propose_facility_projects, with_proposed_facilities
from landmark_field_network.reconcile import FiscalReconcileReport, reconcile_plan
from landmark_field_network.scenarios import Scenario, ScenarioEvaluation, evaluate_plan_scenarios

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
