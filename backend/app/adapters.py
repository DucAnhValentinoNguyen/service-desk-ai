from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ToolAdapter(Protocol):
    name: str


@dataclass
class SupplyChainAdapter:
    name: str = "erp-simulator"

    def inventory(self, item: str = "gateway batteries") -> dict[str, Any]:
        return {"item": item, "available_units": 12, "reorder_point": 20, "open_po": "PO-2048", "promised_date": "2026-08-20", "status": "late"}

    def propose_expedite(self, item: str, idempotency_key: str) -> dict[str, Any]:
        return {"external_id": "ERP-DRAFT-2048", "item": item, "status": "drafted", "idempotency_key": idempotency_key}


@dataclass
class CRMAdapter:
    name: str = "crm-simulator"

    def find_customer(self, query: str) -> dict[str, Any]:
        return {"customer_id": "CUS-1007", "name": "Jordan Example", "device_id": "enocean-room-01", "entitlement": "standard", "match": query[:80]}

    def link_case(self, customer_id: str, summary: str) -> dict[str, Any]:
        return {"case_id": "CRM-7781", "customer_id": customer_id, "status": "linked", "summary": summary}


@dataclass
class HRAdapter:
    name: str = "hrm-simulator"

    def employee_context(self, requester: str) -> dict[str, Any]:
        return {"employee_id": "EMP-42", "requester": requester, "balance_days": 8, "manager_approval_required": True}

    def draft_leave(self, employee_id: str, days: int, idempotency_key: str) -> dict[str, Any]:
        return {"external_id": "HR-DRAFT-42", "employee_id": employee_id, "days": days, "status": "drafted", "idempotency_key": idempotency_key}


@dataclass
class TicketingAdapter:
    name: str = "canonical-ticketing"


@dataclass
class CalendarAdapter:
    name: str = "calendar-simulator"
