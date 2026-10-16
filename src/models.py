from __future__ import annotations

import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    INGESTING = "ingesting"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class Review(BaseModel):
    id: str
    text: str
    rating: Optional[int] = None
    date: Optional[datetime.date] = None
    source: Optional[str] = None


class Theme(BaseModel):
    name: str
    summary: str
    review_count: int = 0
    review_ids: list[str] = Field(default_factory=list)


class Quote(BaseModel):
    text: str
    review_id: str
    date: Optional[datetime.date] = None
    rating: Optional[int] = None


class FeeIssue(BaseModel):
    name: str
    why_confused: str
    evidence_quote: str
    evidence_review_id: str


class IntelligenceResult(BaseModel):
    themes: list[Theme] = Field(default_factory=list)
    top_themes: list[str] = Field(default_factory=list)
    quotes: list[Quote] = Field(default_factory=list)
    fee_issue: Optional[FeeIssue] = None


class WeeklyPulse(BaseModel):
    markdown: str
    word_count: int = 0


class FeeExplainer(BaseModel):
    bullets: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)
    last_checked: Optional[datetime.date] = None


class McpPayload(BaseModel):
    date: datetime.date
    top_themes: list[str] = Field(default_factory=list)
    weekly_pulse: str = ""
    identified_fee_issue: str = "none"
    explanation_bullets: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)


class ToolLog(BaseModel):
    tool: str
    ok: bool
    location: Optional[str] = None
    error: Optional[str] = None
    at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))


class Run(BaseModel):
    id: str
    status: RunStatus = RunStatus.INGESTING
    intelligence: Optional[IntelligenceResult] = None
    pulse: Optional[WeeklyPulse] = None
    explainer: Optional[FeeExplainer] = None
    payload: Optional[McpPayload] = None
    logs: list[ToolLog] = Field(default_factory=list)
    mcp_committed_at: Optional[datetime.datetime] = None
    error: Optional[str] = None

