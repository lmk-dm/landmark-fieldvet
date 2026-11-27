"""Domain objects for network-aware project selection.

A project's value is not a fixed cash-flow profile. It is whatever the network
subproblem returns when that project is (or is not) in the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class Commodity(str, Enum):
    OIL = "oil"
    GAS = "gas"
    WATER = "water"


class NodeKind(str, Enum):
    PAD = "pad"
    CTB = "ctb"
    COMPRESSOR = "compressor"
    PLANT = "plant"
    SALES = "sales"
    DISPOSAL = "disposal"
    JUNCTION = "junction"


class ProjectKind(str, Enum):
    DEVELOPMENT = "development"
    FACILITY = "facility"
    COMMERCIAL = "commercial"


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind


@dataclass(frozen=True)
class Arc:
    """Directed capacity arc. Capacity is shared across projects that flow on it."""

    id: str
    source: str
    target: str
    commodity: Commodity
    base_capacity: float
    """Units per period (bbl or Mcf) at the planning period length."""


@dataclass(frozen=True)
class TypeCurve:
    """Known production profile by age (period index from first production)."""

    oil: tuple[float, ...]
    gas: tuple[float, ...]
    water: tuple[float, ...]

    def __post_init__(self) -> None:
        if not (len(self.oil) == len(self.gas) == len(self.water)):
            raise ValueError("type curve phases must share the same length")

    @property
    def horizon(self) -> int:
        return len(self.oil)

    def at(self, age: int, commodity: Commodity) -> float:
        if age < 0 or age >= self.horizon:
            return 0.0
        if commodity is Commodity.OIL:
            return self.oil[age]
        if commodity is Commodity.GAS:
            return self.gas[age]
        return self.water[age]


@dataclass(frozen=True)
class Project:
    """Candidate project. Starts at most once; timing is a binary per period."""

    id: str
    kind: ProjectKind
    capital: tuple[float, ...]
    """Capital by age from start (period 0 = start period)."""
    earliest_start: int = 0
    lead_time: int = 0
    """Periods from start until the network change / production begins."""
    # Development
    pad_node: str | None = None
    type_curve: TypeCurve | None = None
    # Facility / commercial: capacity added to named arcs once online
    capacity_adds: Mapping[str, float] = field(default_factory=dict)
    # Mutual exclusion / precedence (variant handling)
    excludes: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    group: str | None = None
    """Projects that share a group are mutually exclusive alternatives."""


@dataclass(frozen=True)
class Prices:
    oil: float
    gas: float
    water_disposal: float = 0.0
    discount_rate_per_period: float = 0.01


@dataclass(frozen=True)
class Network:
    nodes: tuple[Node, ...]
    arcs: tuple[Arc, ...]

    def __post_init__(self) -> None:
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("duplicate node id")
        for arc in self.arcs:
            if arc.source not in ids or arc.target not in ids:
                raise ValueError(f"arc {arc.id} references unknown node")

    def arc_by_id(self) -> dict[str, Arc]:
        return {a.id: a for a in self.arcs}


@dataclass(frozen=True)
class FieldModel:
    """Full FieldVET input for one area."""

    network: Network
    projects: tuple[Project, ...]
    n_periods: int
    prices: Prices
    capital_budget: Sequence[float] | None = None
    """Optional per-period capital caps. None means unconstrained capital."""
    start_candidates: tuple[int, ...] | None = None
    """If set, projects may start only in these periods (coarser timing grid)."""
    fix_to_earliest_start: bool = False
    """If true, each project may start only at its earliest_start (selection + staggered timing)."""

    def project_by_id(self) -> dict[str, Project]:
        return {p.id: p for p in self.projects}

    def allowed_starts(self) -> tuple[int, ...]:
        if self.fix_to_earliest_start:
            epochs = sorted({p.earliest_start for p in self.projects})
            for t in epochs:
                if t < 0 or t >= self.n_periods:
                    raise ValueError(f"earliest_start {t} outside [0, {self.n_periods})")
            return tuple(epochs)
        if self.start_candidates is None:
            return tuple(range(self.n_periods))
        for t in self.start_candidates:
            if t < 0 or t >= self.n_periods:
                raise ValueError(f"start candidate {t} outside [0, {self.n_periods})")
        return self.start_candidates


@dataclass(frozen=True)
class StartDecision:
    """x(j, τ) = 1: project j starts in period τ."""

    project_id: str
    start_period: int


@dataclass(frozen=True)
class Plan:
    """Fixed selection and timing. At most one start per project."""

    starts: tuple[StartDecision, ...]

    def start_map(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.starts:
            if s.project_id in out:
                raise ValueError(f"project {s.project_id} starts more than once")
            out[s.project_id] = s.start_period
        return out
