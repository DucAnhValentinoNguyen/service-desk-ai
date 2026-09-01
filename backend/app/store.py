from __future__ import annotations

import json
import hashlib
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
                    email TEXT NOT NULL, role TEXT NOT NULL, pii_scope TEXT NOT NULL,
                    department TEXT NOT NULL DEFAULT 'general', password_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, content TEXT NOT NULL,
                    source TEXT NOT NULL, requester_name TEXT NOT NULL, requester_email TEXT,
                    requester_id TEXT NOT NULL DEFAULT 'demo-admin',
                    diagnostics_json TEXT NOT NULL DEFAULT '{}',
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
                    status TEXT NOT NULL, checksum TEXT NOT NULL, created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}', source_url TEXT
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
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, user_id TEXT NOT NULL,
                    title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    role TEXT NOT NULL, label TEXT NOT NULL, tone TEXT, content TEXT NOT NULL,
                    confidence REAL, citations_json TEXT NOT NULL DEFAULT '[]', note TEXT,
                    related_request_id TEXT, created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                """
            )
            # Existing demo databases predate login credentials and request ownership.
            # SQLite migrations are deliberately additive so a Docker volume survives upgrades.
            user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            if "department" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN department TEXT NOT NULL DEFAULT 'general'")
            if "password_hash" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
            request_columns = {row["name"] for row in db.execute("PRAGMA table_info(requests)").fetchall()}
            if "requester_id" not in request_columns:
                db.execute("ALTER TABLE requests ADD COLUMN requester_id TEXT NOT NULL DEFAULT 'demo-admin'")
            if "diagnostics_json" not in request_columns:
                db.execute("ALTER TABLE requests ADD COLUMN diagnostics_json TEXT NOT NULL DEFAULT '{}'")
            document_columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)").fetchall()}
            if "metadata_json" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'")
            if "source_url" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN source_url TEXT")
            db.commit()

    def seed(self) -> None:
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM users WHERE id IN ('demo-owner', 'demo-admin', 'demo-member', 'demo-viewer')")
            password = hashlib.sha256("demo123".encode()).hexdigest()
            users = [
                ("duc-anh", "demo-workspace", "Duc-Anh Nguyen", "duc-anh@example.com", "owner", "full", "IT administration", password),
                ("giulia-hr", "demo-workspace", "Giulia Rossi", "giulia@example.com", "admin", "hr", "HR", password),
                ("alex-ops", "demo-workspace", "Alex Morgan", "alex@example.com", "admin", "operational", "CRM and ERP", password),
                ("tim-staff", "demo-workspace", "Tim Keller", "tim@example.com", "member", "self", "Finance", password),
                ("john-customer", "demo-workspace", "John Carter", "john@example.com", "viewer", "self", "Customer", password),
            ]
            db.executemany("INSERT OR REPLACE INTO users (id, workspace_id, name, email, role, pii_scope, department, password_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", users)
            for document_id, title, content, source_type, sensitivity, metadata, source_url in self._knowledge_documents():
                checksum = hashlib.sha256(content.encode()).hexdigest()
                existing = db.execute("SELECT checksum FROM documents WHERE id = ?", (document_id,)).fetchone()
                if existing and existing["checksum"] != checksum:
                    db.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
                db.execute("INSERT OR IGNORE INTO documents (id, workspace_id, title, content, source_type, sensitivity, status, checksum, created_at, metadata_json, source_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (document_id, "demo-workspace", title, content, source_type, sensitivity, "ready", checksum, now(), json.dumps(metadata), source_url))
                db.execute("UPDATE documents SET title = ?, content = ?, source_type = ?, sensitivity = ?, status = 'ready', checksum = ?, metadata_json = ?, source_url = ? WHERE id = ?", (title, content, source_type, sensitivity, checksum, json.dumps(metadata), source_url, document_id))
            db.commit()

    def _knowledge_documents(self) -> list[tuple[str, str, str, str, str, dict[str, Any], str | None]]:
        """Load the reproducible demo corpus from Markdown instead of inline strings."""
        corpus = Path(__file__).with_name("knowledge")
        documents = []
        for path in sorted(corpus.glob("*.md")):
            fields: dict[str, str] = {}
            lines = path.read_text(encoding="utf-8").splitlines()
            in_frontmatter = bool(lines and lines[0].strip() == "---")
            body_start = 1 if in_frontmatter else 0
            if in_frontmatter:
                for index in range(1, len(lines)):
                    line = lines[index].strip()
                    if line == "---":
                        body_start = index + 1
                        break
                    if ":" in line:
                        key, value = line.split(":", 1)
                        fields[key.strip()] = value.strip().strip('"')
            content = "\n".join(lines[body_start:]).strip()
            title = fields.get("title") or next((line[2:].strip() for line in lines[body_start:] if line.startswith("# ")), path.stem)
            product_models = [item.strip() for item in fields.get("product_models", "all").split(",") if item.strip()]
            metadata = {"product_area": fields.get("product_area", "service-desk"), "product_models": product_models, "corpus_file": str(path.relative_to(corpus))}
            documents.append((fields.get("id", f"doc-{path.stem}"), title, content, "markdown", fields.get("sensitivity", "internal"), metadata, fields.get("source_url") or None))
        return documents

    def user(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            return self._row(db.execute("SELECT id, workspace_id, name, email, role, pii_scope, department FROM users WHERE id = ?", (user_id,)).fetchone())

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        with self.connect() as db:
            row = db.execute("SELECT id, workspace_id, name, email, role, pii_scope, department FROM users WHERE lower(email) = lower(?) AND password_hash = ?", (email, password_hash)).fetchone()
            return self._row(row)

    def users(self, workspace_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return self._rows(db.execute("SELECT id, name, email, role, department FROM users WHERE workspace_id = ? ORDER BY role, name", (workspace_id,)).fetchall())

    def _row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def _rows(self, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def _conversation_summary(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        item = self._row(row)
        if not item:
            return None
        item["message_count"] = int(item.get("message_count") or 0)
        return item

    def _conversation_message(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        item = self._row(row)
        if not item:
            return None
        item["citations"] = json.loads(item.pop("citations_json", "[]"))
        return item

    def create_conversation(self, workspace_id: str, user_id: str, title: str = "New chat") -> dict[str, Any]:
        conversation_id = f"conv-{uuid.uuid4().hex[:10]}"
        timestamp = now()
        with self.lock, self.connect() as db:
            db.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_id, workspace_id, user_id, title[:120], timestamp, timestamp),
            )
            db.commit()
        return self.get_conversation(conversation_id, workspace_id, user_id) or {}

    def list_conversations(self, workspace_id: str, user_id: str) -> list[dict[str, Any]]:
        query = """
            SELECT
                c.id,
                c.workspace_id,
                c.user_id,
                c.title,
                c.created_at,
                c.updated_at,
                COUNT(m.id) AS message_count,
                COALESCE(MAX(m.created_at), c.updated_at) AS last_message_at,
                (
                    SELECT content
                    FROM conversation_messages cm
                    WHERE cm.conversation_id = c.id
                    ORDER BY cm.created_at DESC
                    LIMIT 1
                ) AS last_message_preview
            FROM conversations c
            LEFT JOIN conversation_messages m ON m.conversation_id = c.id
            WHERE c.workspace_id = ? AND c.user_id = ?
            GROUP BY c.id, c.workspace_id, c.user_id, c.title, c.created_at, c.updated_at
            ORDER BY c.updated_at DESC
        """
        with self.connect() as db:
            rows = db.execute(query, (workspace_id, user_id)).fetchall()
        return [self._conversation_summary(row) or {} for row in rows]

    def get_conversation(self, conversation_id: str, workspace_id: str, user_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            summary = self._conversation_summary(db.execute(
                """
                SELECT
                    c.id,
                    c.workspace_id,
                    c.user_id,
                    c.title,
                    c.created_at,
                    c.updated_at,
                    COUNT(m.id) AS message_count,
                    COALESCE(MAX(m.created_at), c.updated_at) AS last_message_at,
                    (
                        SELECT content
                        FROM conversation_messages cm
                        WHERE cm.conversation_id = c.id
                        ORDER BY cm.created_at DESC
                        LIMIT 1
                    ) AS last_message_preview
                FROM conversations c
                LEFT JOIN conversation_messages m ON m.conversation_id = c.id
                WHERE c.id = ? AND c.workspace_id = ? AND c.user_id = ?
                GROUP BY c.id, c.workspace_id, c.user_id, c.title, c.created_at, c.updated_at
                """,
                (conversation_id, workspace_id, user_id),
            ).fetchone())
            if not summary:
                return None
            messages = db.execute(
                """
                SELECT id, conversation_id, workspace_id, role, label, tone, content,
                       confidence, citations_json, note, related_request_id, created_at
                FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at
                """,
                (conversation_id,),
            ).fetchall()
        summary["messages"] = [self._conversation_message(row) or {} for row in messages]
        return summary

    def rename_conversation(self, conversation_id: str, workspace_id: str, user_id: str, title: str) -> dict[str, Any] | None:
        with self.lock, self.connect() as db:
            db.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND workspace_id = ? AND user_id = ?",
                (title[:120], now(), conversation_id, workspace_id, user_id),
            )
            db.commit()
        return self.get_conversation(conversation_id, workspace_id, user_id)

    def add_conversation_message(
        self,
        conversation_id: str,
        workspace_id: str,
        user_id: str,
        role: str,
        label: str,
        content: str,
        tone: str | None = None,
        confidence: float | None = None,
        citations: list[dict[str, Any]] | None = None,
        note: str | None = None,
        related_request_id: str | None = None,
    ) -> dict[str, Any] | None:
        message_id = f"msg-{uuid.uuid4().hex[:10]}"
        timestamp = now()
        with self.lock, self.connect() as db:
            owned = db.execute(
                "SELECT 1 FROM conversations WHERE id = ? AND workspace_id = ? AND user_id = ?",
                (conversation_id, workspace_id, user_id),
            ).fetchone()
            if not owned:
                return None
            db.execute(
                """
                INSERT INTO conversation_messages
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    workspace_id,
                    role,
                    label,
                    tone,
                    content,
                    confidence,
                    json.dumps(citations or []),
                    note,
                    related_request_id,
                    timestamp,
                ),
            )
            db.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (timestamp, conversation_id),
            )
            db.commit()
        with self.connect() as db:
            return self._conversation_message(db.execute(
                """
                SELECT id, conversation_id, workspace_id, role, label, tone, content,
                       confidence, citations_json, note, related_request_id, created_at
                FROM conversation_messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone())

    def create_request(self, data: dict[str, Any]) -> dict[str, Any]:
        request_id, timestamp = f"req-{uuid.uuid4().hex[:10]}", now()
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO requests (id, workspace_id, content, source, requester_name, requester_email, requester_id, diagnostics_json, status, category, severity, confidence, rationale, assigned_agent, answer, citations_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (request_id, data["workspace_id"], data["content"], data["source"], data["requester_name"], data.get("requester_email"), data["requester_id"], json.dumps(data.get("diagnostics", {})), "received", "unknown", "medium", 0.0, "Not classified", None, None, "[]", timestamp, timestamp))
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
                row["diagnostics"] = json.loads(row.pop("diagnostics_json", "{}"))
            return row

    def list_requests(self, workspace_id: str, status: str | None = None, requester_id: str | None = None, categories: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        query, args = "SELECT * FROM requests WHERE workspace_id = ?", [workspace_id]
        if status:
            query += " AND status = ?"
            args.append(status)
        if requester_id:
            query += " AND requester_id = ?"
            args.append(requester_id)
        if categories:
            query += f" AND category IN ({', '.join('?' for _ in categories)})"
            args.extend(categories)
        query += " ORDER BY created_at DESC"
        with self.connect() as db:
            rows = self._rows(db.execute(query, args).fetchall())
        for row in rows:
            row["citations"] = json.loads(row.pop("citations_json"))
            row["diagnostics"] = json.loads(row.pop("diagnostics_json", "{}"))
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

    def mark_proposal_executed(self, proposal_id: str) -> None:
        with self.lock, self.connect() as db:
            db.execute("UPDATE proposals SET status = 'executed' WHERE id = ?", (proposal_id,))
            db.commit()

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
            rows = self._rows(db.execute("SELECT id, workspace_id, title, source_type, sensitivity, status, checksum, created_at, metadata_json, source_url FROM documents WHERE workspace_id = ? ORDER BY title", (workspace_id,)).fetchall())
        for row in rows:
            row["metadata"] = json.loads(row.pop("metadata_json", "{}"))
        return rows

    def document(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = self._row(db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone())
            if row:
                row["metadata"] = json.loads(row.pop("metadata_json", "{}"))
            return row

    def add_document(self, data: dict[str, Any], checksum: str) -> dict[str, Any]:
        document_id = f"doc-{uuid.uuid4().hex[:10]}"
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO documents (id, workspace_id, title, content, source_type, sensitivity, status, checksum, created_at, metadata_json, source_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (document_id, data["workspace_id"], data["title"], data["content"], data["source_type"], data["sensitivity"], "uploaded", checksum, now(), json.dumps(data.get("metadata", {})), data.get("source_url")))
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
