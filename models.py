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
