from __future__ import annotations

from typing import Any

from .adapters import CRMAdapter, HRAdapter, SupplyChainAdapter
from .guardrails import inspect_input
from .rag import query
from .providers import get_provider
from .schemas import KnowledgeQuery, RequestClassification
from .store import Store


AGENTS = {"supply_chain": "Supply Chain Specialist", "crm": "CRM Specialist", "hr": "HR Specialist", "appointment": "Scheduling Specialist"}


def classify(content: str) -> RequestClassification:
    text = content.lower()
    if any(word in text for word in ("inventory", "stock", "purchase order", "supplier", "delivery", "reorder", "warehouse")):
        category, confidence = "supply_chain", 0.94
    elif any(word in text for word in ("customer", "client", "crm", "device stopped", "complaint", "case", "support")):
        category, confidence = "crm", 0.9
    elif any(word in text for word in ("employee", "leave", "vacation", "access", "hr", "workplace", "manager")):
        category, confidence = "hr", 0.91
    elif any(word in text for word in ("appointment", "technician", "schedule", "calendar", "meeting")):
        category, confidence = "appointment", 0.9
    elif any(word in text for word in ("how", "what", "policy", "procedure", "explain")):
        category, confidence = "general", 0.72
    else:
        category, confidence = "unknown", 0.32
    severity = "high" if any(word in text for word in ("urgent", "critical", "outage", "blocked", "security")) else "medium"
    safety = inspect_input(content)
    if not safety["safe"]:
        return RequestClassification(category=category, severity="high", confidence=0.1, rationale=f"Safety review required: {', '.join(safety['reasons'])}.", assigned_agent=None)
    ai_route = get_provider().route(content)
    if ai_route:
        ai_category = ai_route.get("category")
        if ai_category in AGENTS or ai_category in {"general", "unknown"}:
            raw_confidence = ai_route.get("confidence", confidence)
            try:
                confidence = max(0.0, min(1.0, float(raw_confidence)))
            except (TypeError, ValueError):
                confidence = 0.0
            severity = ai_route.get("severity") if ai_route.get("severity") in {"low", "medium", "high", "critical"} else severity
            rationale = str(ai_route.get("rationale") or "AI router selected a supported category.")[:1000]
            return RequestClassification(category=ai_category, severity=severity, confidence=confidence, rationale=rationale, assigned_agent=AGENTS.get(ai_category))
    rationale = f"Matched {category.replace('_', ' ')} operational terminology with confidence {confidence:.2f}."
    return RequestClassification(category=category, severity=severity, confidence=confidence, rationale=rationale, assigned_agent=AGENTS.get(category))


def run_specialist(store: Store, request: dict[str, Any]) -> dict[str, Any]:
    classification = classify(request["content"])
    evidence = query(store, KnowledgeQuery(question=request["content"], workspace_id=request["workspace_id"], role="admin"))
    result: dict[str, Any] = {"classification": classification.model_dump(), "evidence": evidence.model_dump(), "proposal": None, "external_read": None}
    if classification.category == "unknown" or classification.confidence < 0.65 or not evidence.grounded:
        result["status"] = "awaiting_human"
        result["reason"] = "The request is unsupported, ambiguous, or lacks approved evidence."
        return result
    text = request["content"].lower()
    if classification.category == "supply_chain":
        inventory = SupplyChainAdapter().inventory()
        result["external_read"] = inventory
        result["proposal"] = {"action_type": "create_purchase_order", "risk": "high", "payload": {"item": inventory["item"], "quantity": inventory["reorder_point"] - inventory["available_units"], "reason": "below reorder point and PO late"}}
    elif classification.category == "crm":
        customer = CRMAdapter().find_customer(request["content"])
        result["external_read"] = customer
        result["proposal"] = {"action_type": "send_customer_response", "risk": "medium", "payload": {"customer_id": customer["customer_id"], "draft": "We have opened a support case and are checking the device diagnostics."}}
    elif classification.category == "hr":
        employee = HRAdapter().employee_context(request["requester_name"])
        result["external_read"] = {"employee_id": employee["employee_id"], "manager_approval_required": employee["manager_approval_required"]}
        if any(word in text for word in ("approve", "reset every", "change access", "terminate")):
            result["proposal"] = {"action_type": "change_employee_access", "risk": "critical", "payload": {"reason": "protected HR request requires explicit review"}}
        elif "leave" in text or "vacation" in text:
            result["proposal"] = {"action_type": "approve_leave", "risk": "high", "payload": {"employee_id": employee["employee_id"], "available_days": employee["balance_days"], "manager_approval_required": True}}
    elif classification.category == "appointment":
        result["proposal"] = {"action_type": "book_appointment", "risk": "medium", "payload": {"requires_caller_confirmation": True}}
    specialist = get_provider().specialist(classification.category, request["content"], evidence.answer)
    if specialist and isinstance(specialist.get("answer"), str):
        result["evidence"]["answer"] = specialist["answer"][:4000]
    allowed_actions = {"supply_chain": "create_purchase_order", "crm": "send_customer_response", "hr": "approve_leave", "appointment": "book_appointment"}
    ai_proposal = specialist.get("proposal") if specialist else None
    if isinstance(ai_proposal, dict) and ai_proposal.get("action_type") == allowed_actions.get(classification.category) and result.get("proposal"):
        result["proposal"]["payload"]["ai_draft"] = str(ai_proposal.get("draft") or "")[:2000]
    result["status"] = "awaiting_approval" if result["proposal"] else "resolved"
    return result
