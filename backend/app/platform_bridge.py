from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

from .config import settings
from .schemas import EvidenceCitation


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]+", re.I)


def _tokens(text: str) -> Counter[str]:
    return Counter(TOKEN_RE.findall(text.lower()))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def platform_root() -> Path:
    return Path(settings.platform_data_path)


def latest_run_id() -> str | None:
    runs_dir = platform_root() / "runs"
    if not runs_dir.exists():
        return None
    candidates = sorted(runs_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0].stem if candidates else None


def platform_overview() -> dict[str, Any]:
    run_id = latest_run_id()
    if not run_id:
        return {"available": False, "message": "No ai-data-platform run artifacts found."}

    root = platform_root()
    summary = _read_json(root / "runs" / f"{run_id}.json")
    features_path = root / "gold" / f"run_id={run_id}" / "sensor_health_features.jsonl"
    features = _read_jsonl(features_path) if features_path.exists() else []
    risky = [row for row in features if row.get("predicted_risk") or row.get("anomalies")]
    risky.sort(key=lambda row: float(row.get("risk_score", 0.0)), reverse=True)
    top_devices = [
        {
            "device_id": row["device_id"],
            "gateway_id": row["gateway_id"],
            "risk_score": row.get("risk_score", 0.0),
            "anomalies": row.get("anomalies", []),
            "battery_pct": row.get("battery_pct"),
            "signal_quality": row.get("signal_quality"),
        }
        for row in risky[:5]
    ]
    return {
        "available": True,
        "run_id": run_id,
        "storage": {
            "root": str(root),
            "gold": str(root / "gold" / f"run_id={run_id}"),
            "knowledge": str(root / "knowledge"),
        },
        "summary": summary,
        "top_risky_devices": top_devices,
    }


def platform_retrieve(question: str, top_k: int = 3) -> dict[str, Any]:
    run_id = latest_run_id()
    if not run_id:
        return {"grounded": False, "confidence": 0.0, "citations": [], "evidence": ""}

    chunks_path = platform_root() / "knowledge" / "chunks" / f"run_id={run_id}" / "chunks.jsonl"
    if not chunks_path.exists():
        return {"grounded": False, "confidence": 0.0, "citations": [], "evidence": "", "run_id": run_id}

    question_tokens = _tokens(question)
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in _read_jsonl(chunks_path):
        chunk_tokens = _tokens(chunk.get("content", ""))
        overlap = sum((question_tokens & chunk_tokens).values()) / max(sum(question_tokens.values()), 1)
        score = round(0.85 * overlap + 0.15 * float(chunk.get("metadata", {}).get("priority", 0.0)), 4)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = scored[:top_k]
    citations = [
        EvidenceCitation(
            document_id=chunk["document_id"],
            title=f"{chunk['title']} (platform)",
            page=chunk.get("chunk_index"),
            section=chunk.get("source_type"),
            chunk_id=chunk["chunk_id"],
            excerpt=chunk["content"][:320],
            score=score,
            source_url=chunk.get("source_uri"),
        )
        for score, chunk in selected
    ]
    evidence = " ".join(citation.excerpt for citation in citations[:2])
    return {
        "grounded": bool(citations),
        "confidence": round(min(0.95, citations[0].score + 0.2), 3) if citations else 0.0,
        "citations": citations,
        "evidence": evidence,
        "run_id": run_id,
    }
