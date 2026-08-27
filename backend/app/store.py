from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import settings


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Small transactional store used locally; the schema maps directly to a Postgres adapter."""

    def __init__(self, database_path: str | None = None) -> None:
        self.path = database_path or settings.database_path
        self.lock = threading.RLock()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init_schema(self) -> None:
        with self.lock, self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
                    email TEXT NOT NULL, role TEXT NOT NULL, pii_scope TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, content TEXT NOT NULL,
                    source TEXT NOT NULL, requester_name TEXT NOT NULL, requester_email TEXT,
                    status TEXT NOT NULL, category TEXT NOT NULL, severity TEXT NOT NULL,
                    confidence REAL NOT NULL, rationale TEXT NOT NULL, assigned_agent TEXT,
                    answer TEXT, citations_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL, status TEXT NOT NULL, priority TEXT NOT NULL,
                    category TEXT NOT NULL, assignee TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS comments (
                    id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, author TEXT NOT NULL,
                    body TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY, request_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    action_type TEXT NOT NULL, payload_json TEXT NOT NULL, risk TEXT NOT NULL,
                    approval_required INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    status TEXT NOT NULL, requested_by TEXT NOT NULL, decided_by TEXT,
                    note TEXT, created_at TEXT NOT NULL, decided_at TEXT
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, actor TEXT NOT NULL,
                    action TEXT NOT NULL, target TEXT NOT NULL, model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL, tool_name TEXT, decision TEXT NOT NULL,
                    approval_id TEXT, idempotency_key TEXT, external_response_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, title TEXT NOT NULL,
                    content TEXT NOT NULL, source_type TEXT NOT NULL, sensitivity TEXT NOT NULL,
                    status TEXT NOT NULL, checksum TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    content TEXT NOT NULL, page INTEGER, section TEXT, keywords TEXT NOT NULL,
                    embedding TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS calls (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, caller_name TEXT NOT NULL,
                    caller_email TEXT, line_busy INTEGER NOT NULL, status TEXT NOT NULL,
                    request_id TEXT, transcript_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS appointments (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, call_id TEXT,
                    request_id TEXT, slot_id TEXT NOT NULL UNIQUE, service_type TEXT NOT NULL,
                    caller_name TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                """
            )

    def seed(self) -> None:
        with self.lock, self.connect() as db:
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return
            users = [
                ("demo-owner", "demo-workspace", "Duc (Owner)", "owner@example.com", "owner", "full"),
                ("demo-admin", "demo-workspace", "Alex (Service Desk)", "admin@example.com", "admin", "operational"),
                ("demo-member", "demo-workspace", "Mina (Employee)", "member@example.com", "member", "self"),
                ("demo-viewer", "demo-workspace", "Sam (Viewer)", "viewer@example.com", "viewer", "aggregate"),
            ]
            db.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", users)
            documents = [
                ("doc-supply-policy", "Supply Chain Reorder and Late PO Policy", "For gateway batteries, the reorder point is 20 units. A purchase order more than 48 hours late is a supplier-risk exception. Service desk staff may draft an expedite request, but changing a purchase order requires an operations manager approval.\n\nSection: Inventory exceptions\nOperators should check available stock, open purchase orders, and the promised delivery date before recommending an action.", "markdown", "internal"),
                ("doc-crm-support", "Room Sensor Customer Support Playbook", "When a customer reports missing room-sensor readings, verify the device identifier, last-seen timestamp, signal quality, and installation power conditions. Create or link a CRM case and provide troubleshooting steps. Customer-facing messages require approval when they include compensation, cancellation, or a commitment.", "markdown", "internal"),
                ("doc-hr-leave", "Employee Leave Policy", "Employees may request annual leave through the HR service desk. The manager approval and remaining balance must be checked before approval. The service desk may explain policy and draft a leave request, but it must not approve leave or expose another employee's balance.", "markdown", "restricted"),
                ("doc-appointments", "Technician Appointment Policy", "Technician appointments are offered only from available calendar slots. The caller must confirm the selected time. A booking is idempotent and must not replace an existing appointment. If no suitable slot exists, offer alternatives or escalate to a human coordinator.", "markdown", "internal"),
                ("doc-escalation", "Service Desk Escalation Policy", "Escalate requests when classification confidence is below 0.65, the request asks for an irreversible or protected change, identity is insufficient, the caller is abusive, or the knowledge base does not contain supporting evidence. Record the reason in the ticket timeline.", "markdown", "public"),
            ]
            import hashlib
            for document_id, title, content, source_type, sensitivity in documents:
                checksum = hashlib.sha256(content.encode()).hexdigest()
                db.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (document_id, "demo-workspace", title, content, source_type, sensitivity, "ready", checksum, now()))
            db.commit()

    def _row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def _rows(self, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def create_request(self, data: dict[str, Any]) -> dict[str, Any]:
        request_id, timestamp = f"req-{uuid.uuid4().hex[:10]}", now()
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (request_id, data["workspace_id"], data["content"], data["source"], data["requester_name"], data.get("requester_email"), "received", "unknown", "medium", 0.0, "Not classified", None, None, "[]", timestamp, timestamp))
            db.commit()
        return self.get_request(request_id) or {}

    def update_request(self, request_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {"status", "category", "severity", "confidence", "rationale", "assigned_agent", "answer", "citations_json"}
        updates = [(key, value) for key, value in fields.items() if key in allowed]
        if not updates:
            return self.get_request(request_id)
        updates.append(("updated_at", now()))
        sql = ", ".join(f"{key} = ?" for key, _ in updates)
        with self.lock, self.connect() as db:
            db.execute(f"UPDATE requests SET {sql} WHERE id = ?", [value for _, value in updates] + [request_id])
            db.commit()
        return self.get_request(request_id)

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = self._row(db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone())
            if row:
                row["citations"] = json.loads(row.pop("citations_json"))
            return row

    def list_requests(self, workspace_id: str, status: str | None = None) -> list[dict[str, Any]]:
        query, args = "SELECT * FROM requests WHERE workspace_id = ?", [workspace_id]
        if status:
            query += " AND status = ?"
            args.append(status)
        query += " ORDER BY created_at DESC"
        with self.connect() as db:
            rows = self._rows(db.execute(query, args).fetchall())
        for row in rows:
            row["citations"] = json.loads(row.pop("citations_json"))
        return rows

    def create_ticket(self, request: dict[str, Any]) -> dict[str, Any]:
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (ticket_id, request["id"], request["workspace_id"], request["content"][:90], "open", request["severity"], request["category"], request.get("assigned_agent"), now(), now()))
            db.commit()
        return self.get_ticket(ticket_id) or {}

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            ticket = self._row(db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone())
            if not ticket:
                return None
            ticket["comments"] = self._rows(db.execute("SELECT * FROM comments WHERE ticket_id = ? ORDER BY created_at", (ticket_id,)).fetchall())
            return ticket

    def ticket_for_request(self, request_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT id FROM tickets WHERE request_id = ?", (request_id,)).fetchone()
        return self.get_ticket(row["id"]) if row else None

    def list_tickets(self, workspace_id: str, status: str | None = None) -> list[dict[str, Any]]:
        query, args = "SELECT * FROM tickets WHERE workspace_id = ?", [workspace_id]
        if status:
            query += " AND status = ?"
            args.append(status)
        query += " ORDER BY created_at DESC"
        with self.connect() as db:
            return self._rows(db.execute(query, args).fetchall())

    def add_comment(self, ticket_id: str, author: str, body: str) -> dict[str, Any] | None:
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO comments VALUES (?, ?, ?, ?, ?)", (f"cmt-{uuid.uuid4().hex[:8]}", ticket_id, author, body, now()))
            db.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now(), ticket_id))
            db.commit()
        return self.get_ticket(ticket_id)

    def transition_ticket(self, ticket_id: str, status: str) -> dict[str, Any] | None:
        with self.lock, self.connect() as db:
            db.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (status, now(), ticket_id))
            db.commit()
        return self.get_ticket(ticket_id)

    def create_proposal(self, request_id: str, workspace_id: str, action_type: str, payload: dict[str, Any], risk: str, approval_required: bool) -> dict[str, Any]:
        proposal_id = f"prop-{uuid.uuid4().hex[:10]}"
        status = "awaiting_approval" if approval_required else "proposed"
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO proposals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (proposal_id, request_id, workspace_id, action_type, json.dumps(payload), risk, int(approval_required), status, now()))
            if approval_required:
                db.execute("INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (f"apr-{uuid.uuid4().hex[:10]}", proposal_id, workspace_id, "pending", "service-desk-ai", None, None, now(), None))
            db.commit()
        return self.get_proposal(proposal_id) or {}

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = self._row(db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone())
            if not row:
                return None
            row["payload"] = json.loads(row.pop("payload_json"))
            approval = self._row(db.execute("SELECT * FROM approvals WHERE proposal_id = ?", (proposal_id,)).fetchone())
            row["approval"] = approval
            return row

    def list_approvals(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = self._rows(db.execute("SELECT * FROM approvals WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)).fetchall())
            for row in rows:
                row["proposal"] = self.get_proposal(row["proposal_id"])
            return rows

    def decide_approval(self, approval_id: str, status: str, decided_by: str, note: str | None) -> dict[str, Any] | None:
        with self.lock, self.connect() as db:
            approval = db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if not approval or approval["status"] != "pending":
                return self._row(approval)
            timestamp = now()
            db.execute("UPDATE approvals SET status = ?, decided_by = ?, note = ?, decided_at = ? WHERE id = ?", (status, decided_by, note, timestamp, approval_id))
            db.execute("UPDATE proposals SET status = ? WHERE id = ?", ("approved" if status == "approved" else "rejected", approval["proposal_id"]))
            db.commit()
        with self.connect() as db:
            return self._row(db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())

    def audit(self, workspace_id: str, actor: str, action: str, target: str, decision: str, model: str = "demo-router-v1", prompt_version: str = "service-desk-v1", tool_name: str | None = None, approval_id: str | None = None, idempotency_key: str | None = None, external_response: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {"id": f"aud-{uuid.uuid4().hex[:10]}", "workspace_id": workspace_id, "actor": actor, "action": action, "target": target, "model": model, "prompt_version": prompt_version, "tool_name": tool_name, "decision": decision, "approval_id": approval_id, "idempotency_key": idempotency_key, "external_response_json": json.dumps(external_response) if external_response else None, "created_at": now()}
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO audit_events VALUES (:id, :workspace_id, :actor, :action, :target, :model, :prompt_version, :tool_name, :decision, :approval_id, :idempotency_key, :external_response_json, :created_at)", event)
            db.commit()
        event["external_response"] = external_response
        event.pop("external_response_json")
        return event

    def timeline(self, workspace_id: str, target: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = self._rows(db.execute("SELECT * FROM audit_events WHERE workspace_id = ? AND target = ? ORDER BY created_at", (workspace_id, target)).fetchall())
        for row in rows:
            row["external_response"] = json.loads(row.pop("external_response_json")) if row.get("external_response_json") else None
        return rows

    def documents(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return self._rows(db.execute("SELECT id, workspace_id, title, source_type, sensitivity, status, checksum, created_at FROM documents WHERE workspace_id = ? ORDER BY title", (workspace_id,)).fetchall())

    def document(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            return self._row(db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone())

    def add_document(self, data: dict[str, Any], checksum: str) -> dict[str, Any]:
        document_id = f"doc-{uuid.uuid4().hex[:10]}"
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (document_id, data["workspace_id"], data["title"], data["content"], data["source_type"], data["sensitivity"], "uploaded", checksum, now()))
            db.commit()
        return self.document(document_id) or {}

    def replace_chunks(self, document_id: str, workspace_id: str, chunks: list[dict[str, Any]]) -> None:
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            db.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [(item["id"], document_id, workspace_id, item["content"], item.get("page"), item.get("section"), json.dumps(item["keywords"]), "[]") for item in chunks])
            db.execute("UPDATE documents SET status = 'ready' WHERE id = ?", (document_id,))
            db.commit()

    def chunks(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = self._rows(db.execute("SELECT c.*, d.title FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.workspace_id = ?", (workspace_id,)).fetchall())
        for row in rows:
            row["keywords"] = json.loads(row["keywords"])
        return rows

    def create_call(self, data: dict[str, Any]) -> dict[str, Any]:
        call_id = f"call-{uuid.uuid4().hex[:10]}"
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO calls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (call_id, data["workspace_id"], data["caller_name"], data.get("caller_email"), int(data["line_busy"]), "active", None, "[]", now()))
            db.commit()
        return self.call(call_id) or {}

    def call(self, call_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = self._row(db.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone())
        if row:
            row["transcript"] = json.loads(row.pop("transcript_json"))
        return row

    def update_call(self, call_id: str, **fields: Any) -> dict[str, Any] | None:
        if "transcript" in fields:
            fields["transcript_json"] = json.dumps(fields.pop("transcript"))
        allowed = {"status", "request_id", "transcript_json"}
        updates = [(key, value) for key, value in fields.items() if key in allowed]
        if not updates:
            return self.call(call_id)
        with self.lock, self.connect() as db:
            db.execute(f"UPDATE calls SET {', '.join(f'{key} = ?' for key, _ in updates)} WHERE id = ?", [value for _, value in updates] + [call_id])
            db.commit()
        return self.call(call_id)

    def appointment_slots(self) -> list[dict[str, Any]]:
        base = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
        slots = []
        for day in range(1, 4):
            for hour in (10, 11, 14, 15, 16):
                slot = base + timedelta(days=day, hours=hour - 9)
                slots.append({"slot_id": slot.strftime("slot-%Y%m%d-%H%M"), "starts_at": slot.isoformat(), "duration_minutes": 60, "available": True})
        with self.connect() as db:
            booked = {row["slot_id"] for row in db.execute("SELECT slot_id FROM appointments WHERE status = 'confirmed'").fetchall()}
        for slot in slots:
            slot["available"] = slot["slot_id"] not in booked
        return slots

    def book_appointment(self, data: dict[str, Any]) -> dict[str, Any]:
        appointment_id = f"apt-{uuid.uuid4().hex[:10]}"
        with self.lock, self.connect() as db:
            existing = db.execute("SELECT * FROM appointments WHERE slot_id = ?", (data["slot_id"],)).fetchone()
            if existing:
                existing_item = self._row(existing) or {}
                if existing_item.get("call_id") == data.get("call_id"):
                    return existing_item
                return {"conflict": True, "slot_id": data["slot_id"], "status": "unavailable"}
            db.execute("INSERT INTO appointments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (appointment_id, data["workspace_id"], data.get("call_id"), data.get("request_id"), data["slot_id"], data["service_type"], data["caller_name"], "confirmed", now()))
            db.commit()
        with self.connect() as db:
            return self._row(db.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()) or {}

    def appointment_for_call(self, call_id: str, slot_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            return self._row(db.execute("SELECT * FROM appointments WHERE call_id = ? AND slot_id = ?", (call_id, slot_id)).fetchone())

    def integrations(self) -> list[dict[str, Any]]:
        return [{"name": name, "kind": kind, "status": "healthy", "mode": "simulator"} for name, kind in [("Ticketing", "canonical"), ("ERP", "supply_chain"), ("CRM", "customer_support"), ("HRM", "people_operations"), ("Calendar", "scheduling"), ("Knowledge base", "rag")]]


store = Store()
