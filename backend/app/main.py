from __future__ import annotations

from contextlib import asynccontextmanager
import hashlib
import json
import os
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .agents import classify, looks_like_knowledge_query, run_specialist
from .config import settings
from .guardrails import can_approve, inspect_input, redact_hr, requires_approval
from .platform_bridge import platform_overview
from .rag import ensure_index, ingest_document, query
from .schemas import (
    ApprovalDecision, CallCreate, CallMessage, CommentCreate, DocumentCreate, LoginRequest,
    EvaluationCreate, KnowledgeQuery, ProposalCreate, ScheduleRequest,
    ServiceRequestCreate, TransitionCreate,
)
from .store import Store, now, store


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.seed()
    ensure_index(store)
    yield


app = FastAPI(title="Service Desk AI", version="0.1.0", description="Guarded ERP, CRM, HRM, RAG, ticketing, and call orchestration demo", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def actor_context(x_demo_user: str | None, x_workspace_id: str | None) -> tuple[str, str, str]:
    # Legacy ids keep existing API scripts working while the browser uses DB-backed users.
    aliases = {"demo-owner": "duc-anh", "demo-admin": "alex-ops", "demo-member": "tim-staff", "demo-viewer": "john-customer"}
    user_id = aliases.get(x_demo_user or "duc-anh", x_demo_user or "duc-anh")
    user = store.user(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    workspace, role = user["workspace_id"], user["role"]
    if x_workspace_id and x_workspace_id != workspace:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    return user_id, workspace, role


def allowed_categories(user_id: str, role: str) -> tuple[str, ...] | None:
    if role == "owner":
        return None
    if role != "admin":
        return ()
    department = (store.user(user_id) or {}).get("department")
    return ("hr",) if department == "HR" else ("supply_chain", "crm", "appointment", "general", "unknown")


def require_request_access(item: dict[str, Any], user_id: str, workspace: str, role: str) -> None:
    if item["workspace_id"] != workspace:
        raise HTTPException(status_code=404, detail="Request not found")
    categories = allowed_categories(user_id, role)
    if role == "owner" or item["requester_id"] == user_id:
        return
    if categories and item["category"] in categories:
        return
    raise HTTPException(status_code=404, detail="Request not found")


def request_bundle(request_id: str) -> dict[str, Any]:
    request = store.get_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    request["ticket"] = store.ticket_for_request(request_id)
    proposals = []
    for approval in store.list_approvals(request["workspace_id"]):
        proposal = approval.get("proposal")
        if proposal and proposal["request_id"] == request_id:
            proposals.append(proposal)
    request["proposals"] = proposals
    return request


def apply_triage(request_id: str, actor: str = "service-desk-ai") -> dict[str, Any]:
    request = store.get_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    result = run_specialist(store, request)
    classification = result["classification"]
    status = result["status"]
    if result.get("proposal") and requires_approval(result["proposal"]["action_type"]):
        status = "awaiting_approval"
    store.update_request(request_id, status=status, category=classification["category"], severity=classification["severity"], confidence=classification["confidence"], rationale=classification["rationale"], assigned_agent=classification.get("assigned_agent"), answer=result["evidence"]["answer"], citations_json=json.dumps(result["evidence"]["citations"]))
    ticket = store.ticket_for_request(request_id)
    if not ticket:
        ticket = store.create_ticket(store.get_request(request_id) or request)
    elif status == "awaiting_human":
        store.transition_ticket(ticket["id"], "pending")
    if result.get("proposal"):
        proposal = result["proposal"]
        created = store.create_proposal(request_id, request["workspace_id"], proposal["action_type"], proposal["payload"], proposal["risk"], requires_approval(proposal["action_type"]))
        store.audit(request["workspace_id"], actor, "proposal.created", request_id, "awaiting_approval" if created["approval_required"] else "proposed", tool_name=classification.get("assigned_agent"))
    decision = "escalated" if status == "awaiting_human" else "classified"
    store.audit(request["workspace_id"], actor, "request.triaged", request_id, decision, tool_name=classification.get("assigned_agent"))
    return request_bundle(request_id)


def create_human_escalation(question: str, actor: str, workspace: str, reason: str) -> dict[str, Any]:
    identity = store.user(actor) or {}
    request = store.create_request({"content": question, "source": "web", "requester_id": actor, "requester_name": identity.get("name", actor), "requester_email": identity.get("email"), "workspace_id": workspace})
    store.update_request(request["id"], status="awaiting_human", rationale=reason, severity="medium", confidence=0.0)
    ticket = store.create_ticket(store.get_request(request["id"]) or request)
    store.transition_ticket(ticket["id"], "pending")
    store.audit(workspace, actor, "knowledge.escalated", request["id"], "human_review", tool_name="rag")
    return {"request_id": request["id"], "ticket_id": ticket["id"]}


def process_request(payload: ServiceRequestCreate, actor: str, workspace: str) -> dict[str, Any]:
    safety = inspect_input(payload.content)
    identity = store.user(actor) or {}
    request = store.create_request({**payload.model_dump(), "workspace_id": workspace, "requester_id": actor, "requester_name": identity.get("name", actor), "requester_email": identity.get("email")})
    store.audit(workspace, actor, "request.created", request["id"], "accepted" if safety["safe"] else "blocked", tool_name="intake-guardrail")
    if not safety["safe"]:
        store.update_request(request["id"], status="awaiting_human", rationale=f"Human review required: {', '.join(safety['reasons'])}", severity="high", confidence=0.0)
        ticket = store.create_ticket(store.get_request(request["id"]) or request)
        store.transition_ticket(ticket["id"], "pending")
        return request_bundle(request["id"])
    return apply_triage(request["id"], actor)


def process_knowledge(
    question: str,
    actor: str,
    workspace: str,
    role: str,
    answer_mode: str = "explain",
    product_model: str | None = None,
    firmware_version: str | None = None,
) -> dict[str, Any]:
    result = query(
        store,
        KnowledgeQuery(
            question=question,
            workspace_id=workspace,
            role=role,
            answer_mode=answer_mode,
            product_model=product_model,
            firmware_version=firmware_version,
        ),
    ).model_dump()
    warning = str(result.get("warning") or "")
    if not result["grounded"] and "Prompt-injection attempt detected" not in warning:
        result["escalation"] = create_human_escalation(question, actor, workspace, result.get("warning") or "Knowledge answer requires human review")
    return result

@app.get("/")
def root() -> dict[str, str]:
    return {"service": "service-desk-ai", "docs": "/docs", "health": "/healthz"}


@app.get("/healthz")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "provider": settings.model_provider,
        "storage": "sqlite-local",
        "platform_data_path": settings.platform_data_path,
        "platform_available": platform_overview().get("available", False),
        "version": app.version,
    }


@app.get("/v1/platform/overview")
def platform_status(x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor_context(x_demo_user, x_workspace_id)
    return platform_overview()


@app.post("/v1/auth/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    user = store.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return user


@app.get("/v1/auth/demo-users")
def demo_users() -> list[dict[str, Any]]:
    return store.users("demo-workspace")


@app.get("/v1/me")
def me(x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, str]:
    user, workspace, role = actor_context(x_demo_user, x_workspace_id)
    return store.user(user) or {"user_id": user, "workspace_id": workspace, "role": role}


@app.post("/v1/requests")
def create_request(payload: ServiceRequestCreate, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    if payload.workspace_id != workspace:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    return process_request(payload, actor, workspace)


@app.post("/v1/intake")
def intake(payload: ServiceRequestCreate, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    if payload.workspace_id != workspace:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    safety = inspect_input(payload.content)
    route = classify(payload.content).model_dump()
    if "prompt_injection" in safety["reasons"]:
        return {"kind": "knowledge", "route": route, "knowledge": process_knowledge(payload.content, actor, workspace, role)}
    if looks_like_knowledge_query(payload.content):
        return {"kind": "knowledge", "route": route, "knowledge": process_knowledge(payload.content, actor, workspace, role)}
    return {"kind": "request", "route": route, "request": process_request(payload, actor, workspace)}


@app.get("/v1/requests")
def list_requests(status: str | None = Query(default=None), x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> list[dict[str, Any]]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    if role in {"member", "viewer"}:
        return store.list_requests(workspace, status, requester_id=actor)
    visible = store.list_requests(workspace, status, categories=allowed_categories(actor, role))
    if role == "admin":
        own = store.list_requests(workspace, status, requester_id=actor)
        return sorted({item["id"]: item for item in [*visible, *own]}.values(), key=lambda item: item["created_at"], reverse=True)
    return visible


@app.get("/v1/requests/{request_id}")
def get_request(request_id: str, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    item = request_bundle(request_id)
    require_request_access(item, actor, workspace, role)
    return item


@app.post("/v1/requests/{request_id}/triage")
def triage_request(request_id: str, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    item = store.get_request(request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Request not found")
    require_request_access(item, actor, workspace, role)
    return apply_triage(request_id, actor)


@app.get("/v1/tickets")
def list_tickets(status: str | None = Query(default=None), x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> list[dict[str, Any]]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    requests = list_requests(status=None, x_demo_user=x_demo_user, x_workspace_id=x_workspace_id)
    visible_ids = {item["id"] for item in requests}
    return [item for item in store.list_tickets(workspace, status) if item["request_id"] in visible_ids]


@app.get("/v1/tickets/{ticket_id}")
def get_ticket(ticket_id: str, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    ticket = store.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    request = store.get_request(ticket["request_id"])
    if not request:
        raise HTTPException(status_code=404, detail="Ticket not found")
    require_request_access(request, actor, workspace, role)
    return ticket


@app.post("/v1/tickets/{ticket_id}/comment")
def add_comment(ticket_id: str, payload: CommentCreate, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, _ = actor_context(x_demo_user, x_workspace_id)
    ticket = get_ticket(ticket_id, x_demo_user, x_workspace_id)
    result = store.add_comment(ticket_id, actor, payload.body)
    store.audit(workspace, actor, "ticket.comment_added", ticket_id, "written")
    return result or ticket


@app.post("/v1/tickets/{ticket_id}/transition")
def transition_ticket(ticket_id: str, payload: TransitionCreate, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    if role in {"viewer", "member"}:
        raise HTTPException(status_code=403, detail="Only IT and operational staff can transition tickets")
    get_ticket(ticket_id, x_demo_user, x_workspace_id)
    result = store.transition_ticket(ticket_id, payload.status)
    store.audit(workspace, actor, "ticket.transitioned", ticket_id, payload.status)
    return result or {}


@app.post("/v1/requests/{request_id}/proposals")
def create_proposal(request_id: str, payload: ProposalCreate, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    if role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only operational staff can create action proposals")
    request = get_request(request_id, x_demo_user, x_workspace_id)
    created = store.create_proposal(request_id, workspace, payload.action_type, payload.payload, "high" if requires_approval(payload.action_type) else "low", requires_approval(payload.action_type))
    store.audit(workspace, actor, "proposal.created", request_id, "awaiting_approval" if created["approval_required"] else "proposed")
    return created


@app.get("/v1/approvals")
def approvals(x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> list[dict[str, Any]]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    if role == "owner":
        return store.list_approvals(workspace)
    categories = allowed_categories(actor, role)
    return [item for item in store.list_approvals(workspace) if categories and (store.get_request(item["proposal"]["request_id"]) or {}).get("category") in categories]


def execute_approved(proposal: dict[str, Any], approval_id: str, actor: str) -> dict[str, Any]:
    request_id = proposal["request_id"]
    request = store.get_request(request_id) or {}
    action = proposal["action_type"]
    if action == "book_appointment":
        slot = next((item for item in store.appointment_slots() if item["available"]), None)
        if not slot:
            raise HTTPException(status_code=409, detail="No appointment slots are available")
        response = store.book_appointment({"workspace_id": request["workspace_id"], "request_id": request_id, "slot_id": slot["slot_id"], "service_type": "Technician visit", "caller_name": request["requester_name"]})
    else:
        response = {"action": action, "status": "executed-in-simulator", "external_id": f"SIM-{uuid.uuid4().hex[:8].upper()}"}
    store.audit(request.get("workspace_id", "demo-workspace"), actor, "proposal.executed", request_id, "approved", tool_name=action, approval_id=approval_id, idempotency_key=f"{proposal['id']}:approved", external_response=response)
    store.update_request(request_id, status="resolved")
    ticket = store.ticket_for_request(request_id)
    if ticket:
        store.transition_ticket(ticket["id"], "resolved")
    store.mark_proposal_executed(proposal["id"])
    return response


@app.post("/v1/approvals/{approval_id}/approve")
def approve(approval_id: str, payload: ApprovalDecision | None = None, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the IT administrator can approve protected actions")
    approvals_list = store.list_approvals(workspace)
    approval = next((item for item in approvals_list if item["id"] == approval_id), None)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    result = store.decide_approval(approval_id, "approved", actor, payload.note if payload else None)
    response = execute_approved(approval["proposal"], approval_id, actor)
    return {"approval": result, "execution": response}


@app.post("/v1/approvals/{approval_id}/reject")
def reject(approval_id: str, payload: ApprovalDecision | None = None, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the IT administrator can reject protected actions")
    approval = next((item for item in store.list_approvals(workspace) if item["id"] == approval_id), None)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    result = store.decide_approval(approval_id, "rejected", actor, payload.note if payload else None)
    store.update_request(approval["proposal"]["request_id"], status="rejected")
    store.audit(workspace, actor, "proposal.rejected", approval["proposal"]["request_id"], "rejected", approval_id=approval_id)
    return {"approval": result}


@app.post("/v1/knowledge/documents")
def create_document(payload: DocumentCreate, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    if role not in {"owner", "admin"} or payload.workspace_id != workspace:
        raise HTTPException(status_code=403, detail="Insufficient permission to upload knowledge")
    checksum = hashlib.sha256(payload.content.encode()).hexdigest()
    document = store.add_document(payload.model_dump(), checksum)
    chunks = ingest_document(store, document["id"])
    store.audit(workspace, actor, "knowledge.document_ingested", document["id"], "ready")
    return {**document, "chunk_count": len(chunks)}


@app.post("/v1/knowledge/documents/{document_id}/ingest")
def ingest(document_id: str, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    _, workspace, _ = actor_context(x_demo_user, x_workspace_id)
    document = store.document(document_id)
    if not document or document["workspace_id"] != workspace:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document_id": document_id, "chunks": len(ingest_document(store, document_id)), "status": "ready"}


@app.get("/v1/knowledge/documents")
def documents(x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> list[dict[str, Any]]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    result = store.documents(workspace)
    if role == "viewer":
        return [item for item in result if item["sensitivity"] == "public"]
    return result


@app.post("/v1/knowledge/query")
def knowledge_query(payload: KnowledgeQuery, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    if payload.workspace_id != workspace:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    return process_knowledge(payload.question, actor, workspace, role, payload.answer_mode, payload.product_model, payload.firmware_version)


@app.post("/v1/knowledge/feedback")
def knowledge_feedback(payload: dict[str, Any], x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, _ = actor_context(x_demo_user, x_workspace_id)
    store.audit(workspace, actor, "knowledge.feedback", str(payload.get("query_id", "unknown")), str(payload.get("label", "unlabelled")))
    return {"accepted": True}


@app.post("/v1/knowledge/evaluations")
def evaluate(payload: EvaluationCreate, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    _, workspace, role = actor_context(x_demo_user, x_workspace_id)
    results = [query(store, item.model_copy(update={"workspace_id": workspace, "role": role})).model_dump() for item in payload.questions]
    grounded = sum(1 for item in results if item["grounded"])
    return {"evaluation_id": f"eval-{uuid.uuid4().hex[:10]}", "questions": len(results), "grounded_rate": grounded / len(results), "results": results}


@app.post("/v1/calls")
def create_call(payload: CallCreate, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, _ = actor_context(x_demo_user, x_workspace_id)
    if payload.workspace_id != workspace:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    call = store.create_call(payload.model_dump())
    greeting = "All service lines are busy. I am the service desk assistant. Please describe your request and I will create a ticket or connect you to a human specialist."
    call["transcript"] = [{"speaker": "assistant", "text": greeting, "at": now()}]
    store.update_call(call["id"], transcript=call["transcript"])
    store.audit(workspace, actor, "call.started", call["id"], "active")
    return store.call(call["id"]) or call


@app.post("/v1/calls/{call_id}/messages")
def call_message(call_id: str, payload: CallMessage, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, _ = actor_context(x_demo_user, x_workspace_id)
    call = store.call(call_id)
    if not call or call["workspace_id"] != workspace:
        raise HTTPException(status_code=404, detail="Call not found")
    transcript = call["transcript"] + [{"speaker": "caller", "text": payload.content, "at": now()}]
    safety = inspect_input(payload.content)
    if not safety["safe"]:
        response = "I cannot safely process that request automatically. I have marked it for a human specialist."
        store.update_call(call_id, status="awaiting_human", transcript=transcript + [{"speaker": "assistant", "text": response, "at": now()}])
        store.audit(workspace, actor, "call.escalated", call_id, "unsafe_input")
        return store.call(call_id) or {}
    request = store.create_request({"content": payload.content, "source": "phone", "requester_id": actor, "requester_name": call["caller_name"], "requester_email": call["caller_email"], "workspace_id": workspace})
    store.update_call(call_id, request_id=request["id"])
    triaged = apply_triage(request["id"], actor)
    answer = redact_hr(triaged.get("answer") or "I created a service request and routed it to the right specialist.", "member")
    transcript.append({"speaker": "assistant", "text": f"I created ticket {triaged['ticket']['id']}. {answer} Say 'schedule an appointment' if you need a technician visit.", "at": now()})
    store.update_call(call_id, transcript=transcript, status="awaiting_approval" if triaged["status"] == "awaiting_approval" else "active")
    return store.call(call_id) or {}


@app.get("/v1/calendar/availability")
def availability(x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> list[dict[str, Any]]:
    actor_context(x_demo_user, x_workspace_id)
    return store.appointment_slots()


@app.post("/v1/calls/{call_id}/schedule")
def schedule(call_id: str, payload: ScheduleRequest, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, role = actor_context(x_demo_user, x_workspace_id)
    call = store.call(call_id)
    if not call or call["workspace_id"] != workspace:
        raise HTTPException(status_code=404, detail="Call not found")
    if not payload.slot_id:
        return {"status": "choose_slot", "slots": store.appointment_slots()}
    existing = store.appointment_for_call(call_id, payload.slot_id)
    if existing:
        return existing
    slot = next((item for item in store.appointment_slots() if item["slot_id"] == payload.slot_id), None)
    if not slot or not slot["available"]:
        raise HTTPException(status_code=409, detail="That appointment slot is no longer available")
    appointment = store.book_appointment({"workspace_id": workspace, "call_id": call_id, "request_id": call.get("request_id"), "slot_id": payload.slot_id, "service_type": payload.service_type, "caller_name": call["caller_name"]})
    if appointment.get("conflict"):
        raise HTTPException(status_code=409, detail="That appointment slot is already booked")
    store.audit(workspace, actor, "appointment.booked", call_id, "confirmed", tool_name="calendar-simulator", idempotency_key=payload.slot_id, external_response=appointment)
    return appointment


@app.get("/v1/workflows/{workflow_id}/timeline")
def timeline(workflow_id: str, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> list[dict[str, Any]]:
    _, workspace, _ = actor_context(x_demo_user, x_workspace_id)
    return store.timeline(workspace, workflow_id)


@app.get("/v1/integrations/health")
def integration_health(x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> list[dict[str, Any]]:
    actor_context(x_demo_user, x_workspace_id)
    return store.integrations()


@app.post("/v1/workflows/{workflow_id}/retry")
def retry_workflow(workflow_id: str, x_demo_user: str | None = Header(default=None), x_workspace_id: str | None = Header(default=None)) -> dict[str, Any]:
    actor, workspace, _ = actor_context(x_demo_user, x_workspace_id)
    if not store.get_request(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    store.audit(workspace, actor, "workflow.retry_requested", workflow_id, "queued")
    return {"workflow_id": workflow_id, "status": "queued"}
