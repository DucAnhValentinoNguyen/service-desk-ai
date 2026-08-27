from __future__ import annotations

import re
from typing import Any

from .rag import contains_injection


ABUSE_RE = re.compile(r"\b(kill|idiot|stupid|shut up)\b", re.I)
PROTECTED_ACTIONS = {
    "create_purchase_order", "modify_purchase_order", "send_supplier_message",
    "send_customer_response", "change_customer_entitlement", "refund_customer",
    "update_hr_record", "approve_leave", "change_employee_access", "book_appointment",
}


def inspect_input(text: str) -> dict[str, Any]:
    reasons: list[str] = []
    if contains_injection(text):
        reasons.append("prompt_injection")
    if ABUSE_RE.search(text):
        reasons.append("abusive_language")
    return {"safe": not reasons, "reasons": reasons}


def requires_approval(action_type: str) -> bool:
    return action_type in PROTECTED_ACTIONS


def can_approve(role: str) -> bool:
    return role in {"owner", "admin"}


def redact_hr(text: str, role: str) -> str:
    if role in {"owner", "admin"}:
        return text
    return re.sub(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", "[redacted person]", text)
