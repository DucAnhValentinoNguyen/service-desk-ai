from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Category = Literal["supply_chain", "crm", "hr", "appointment", "general", "unknown"]
RequestStatus = Literal[
    "received", "categorised", "in_progress", "awaiting_approval", "awaiting_human", "resolved", "rejected"
]
TicketStatus = Literal["open", "in_progress", "pending", "resolved", "closed"]
Role = Literal["owner", "admin", "member", "viewer"]
AnswerMode = Literal["explain", "troubleshoot", "design", "find_documentation"]


class WorkspaceContext(BaseModel):
    workspace_id: str = "demo-workspace"
    user_id: str = "demo-admin"
    role: Role = "admin"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=240)
    password: str = Field(min_length=1, max_length=240)


class ServiceRequestCreate(BaseModel):
    content: str = Field(min_length=3, max_length=8000)
    source: Literal["web", "email", "phone", "api"] = "web"
    requester_name: str = Field(default="Demo requester", max_length=120)
    requester_email: str | None = Field(default=None, max_length=240)
    workspace_id: str = "demo-workspace"
    diagnostics: dict[str, str] = Field(default_factory=dict, max_length=10)


class RequestClassification(BaseModel):
    category: Category
    severity: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    rationale: str
    assigned_agent: str | None = None


class EvidenceCitation(BaseModel):
    document_id: str
    title: str
    page: int | None = None
    section: str | None = None
    chunk_id: str
    excerpt: str
    score: float
    source_url: str | None = None


class KnowledgeQuery(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    workspace_id: str = "demo-workspace"
    role: Role = "member"
    top_k: int = Field(default=5, ge=1, le=10)
    answer_mode: AnswerMode = "explain"
    product_model: str | None = Field(default=None, max_length=120)
    firmware_version: str | None = Field(default=None, max_length=80)


class KnowledgeAnswer(BaseModel):
    answer: str
    grounded: bool
    confidence: float
    citations: list[EvidenceCitation]
    rejected_candidates: list[dict[str, Any]] = []
    warning: str | None = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class TransitionCreate(BaseModel):
    status: TicketStatus


class ProposalCreate(BaseModel):
    action_type: str = Field(min_length=2, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class CallCreate(BaseModel):
    caller_name: str = Field(min_length=1, max_length=120)
    caller_email: str | None = Field(default=None, max_length=240)
    line_busy: bool = True
    workspace_id: str = "demo-workspace"


class CallMessage(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ScheduleRequest(BaseModel):
    service_type: str = Field(min_length=2, max_length=120)
    preferred_date: str | None = None
    preferred_period: Literal["morning", "afternoon", "any"] = "any"
    slot_id: str | None = None


class DocumentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    content: str = Field(min_length=20, max_length=100000)
    source_type: Literal["markdown", "text", "html", "pdf"] = "markdown"
    workspace_id: str = "demo-workspace"
    sensitivity: Literal["public", "internal", "restricted"] = "internal"
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_url: str | None = Field(default=None, max_length=1000)


class EvaluationCreate(BaseModel):
    questions: list[KnowledgeQuery] = Field(min_length=1, max_length=100)
