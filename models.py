"""
Pydantic v2 data models for ra-pm.
All data that flows in/out of tools is validated against these models.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectStatus(str, Enum):
    active   = "active"
    archived = "archived"


class IssueStatus(str, Enum):
    idea        = "idea"
    planned     = "planned"
    in_progress = "in-progress"
    done        = "done"
    blocked     = "blocked"
    cancelled   = "cancelled"


class Priority(str, Enum):
    p0 = "p0"
    p1 = "p1"
    p2 = "p2"
    p3 = "p3"


class Area(str, Enum):
    content  = "content"
    research = "research"
    dev      = "dev"
    ops      = "ops"
    design   = "design"
    infra    = "infra"
    strategy = "strategy"


class Project(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id:             str
    name:           str
    status:         ProjectStatus        = ProjectStatus.active
    workspace_path: Optional[str]        = None
    description:    Optional[str]        = None
    area:           Optional[Area]       = None
    last_touched:   Optional[date]       = None
    created:        Optional[date]       = None


class Issue(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id:         int
    title:      str
    status:     IssueStatus = IssueStatus.idea
    priority:   Priority    = Priority.p2
    area:       Area
    why:        str
    hypothesis: Optional[str] = None
    created:    date          = Field(default_factory=date.today)
    updated:    date          = Field(default_factory=date.today)

    @field_validator("title")
    @classmethod
    def title_max_80(cls, v: str) -> str:
        return v[:80]

    @field_validator("why")
    @classmethod
    def why_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("why is required — every issue needs a strategic rationale")
        return v


class Claim(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id:           int
    claim:        str
    evidence_ref: str
    confidence:   str   # low | medium | high (kept as str for backward compat)
    registered:   Optional[date] = Field(default_factory=date.today)


class Thesis(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    statement:      str
    open_questions: list[str] = []
    claims:         list[Claim] = []
    updated:        date = Field(default_factory=date.today)


class Focus(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    project:     str
    issue_id:    Optional[int]  = None
    issue_title: Optional[str]  = None
    set_at:      Optional[str]  = None


class RaProjectMarker(BaseModel):
    """Serialized to .ra-project.yaml in a project's root directory."""
    model_config = ConfigDict(use_enum_values=True)

    id:          str
    name:        str
    indexed_at:  str            = Field(default_factory=lambda: datetime.now().isoformat())
    description: Optional[str] = None
    area:        Optional[str] = None


class InboxIdea(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    title:             str
    area:              Optional[Area] = None
    why:               str
    hypothesis:        Optional[str]  = None
    priority:          Priority       = Priority.p2
    project:           str            = "inbox"
    created:           Optional[str]  = None
    suggested_project: Optional[str]  = None
    routing_reason:    Optional[str]  = None
    suggested_priority: Optional[str] = None


# ── v2: learning system models ────────────────────────────────────────────────

class BetStatus(str, Enum):
    active      = "active"
    validated   = "validated"
    invalidated = "invalidated"
    paused      = "paused"


class ExperimentStatus(str, Enum):
    running   = "running"
    completed = "completed"
    paused    = "paused"
    abandoned = "abandoned"


class NorthStar(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    metric:             str
    current:            Optional[float] = None
    target:             float
    timeframe:          str
    why_this_metric:    str
    leading_indicators: list[str] = []
    updated:            date = Field(default_factory=date.today)

    @field_validator("why_this_metric")
    @classmethod
    def why_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("why_this_metric is required")
        return v


class TheoryOfChange(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    inputs:      list[str]
    activities:  list[str]
    outputs:     list[str]
    outcomes:    list[str]
    impact:      str
    assumptions: list[str]
    updated:     date = Field(default_factory=date.today)

    @field_validator("assumptions")
    @classmethod
    def assumptions_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("assumptions required — what must be true for the causal chain to hold?")
        return v


class Bet(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id:              int
    statement:       str
    rationale:       str
    confidence:      float = Field(ge=0.0, le=1.0)
    evidence_needed: str
    status:          BetStatus = BetStatus.active
    created:         date = Field(default_factory=date.today)
    updated:         date = Field(default_factory=date.today)
    updates:         list[dict] = []  # log of confidence changes

    @field_validator("rationale", "evidence_needed")
    @classmethod
    def required_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field is required")
        return v


class Experiment(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id:               int
    hypothesis:       str
    bet_id:           int
    method:           str
    expected_learning: str
    status:           ExperimentStatus = ExperimentStatus.running
    started:          date = Field(default_factory=date.today)
    completed:        Optional[date] = None

    @field_validator("hypothesis", "method", "expected_learning")
    @classmethod
    def required_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field is required")
        return v


class Finding(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id:               int
    experiment_id:    int
    result:           str
    implication:      str
    confidence_delta: float
    source:           str
    logged:           date = Field(default_factory=date.today)

    @field_validator("implication", "result")
    @classmethod
    def required_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field is required")
        return v


class Decision(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id:                    int
    decision:              str
    rationale:             str
    alternatives_rejected: list[str] = []
    bets_affected:         list[int] = []
    logged:                date = Field(default_factory=date.today)

    @field_validator("rationale", "decision")
    @classmethod
    def required_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field is required")
        return v
