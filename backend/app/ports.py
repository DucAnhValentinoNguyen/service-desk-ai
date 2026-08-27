from __future__ import annotations

from typing import Any, Protocol


class ObjectStore(Protocol):
    def put(self, key: str, content: bytes, content_type: str) -> str: ...
    def get(self, key: str) -> bytes: ...


class JobQueue(Protocol):
    def enqueue(self, kind: str, payload: dict[str, Any], idempotency_key: str) -> str: ...


class IdentityProvider(Protocol):
    def verify(self, token: str) -> dict[str, str]: ...


class LocalObjectStore:
    """Development implementation; production uses an S3-backed adapter."""

    def __init__(self, root: str = "data/objects") -> None:
        from pathlib import Path

        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        destination = self.root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return str(destination)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


class DemoIdentityProvider:
    def verify(self, token: str) -> dict[str, str]:
        return {"user_id": token or "demo-admin", "workspace_id": "demo-workspace", "role": "admin"}
