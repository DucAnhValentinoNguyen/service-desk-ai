from __future__ import annotations

import re
import uuid
from typing import Any

from .schemas import EvidenceCitation, KnowledgeAnswer, KnowledgeQuery
from .providers import get_provider
from .store import Store


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]+", re.I)
INJECTION_RE = re.compile(r"ignore (all|any|the) previous|reveal (the )?system|developer message|bypass (the )?policy", re.I)


def tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def contains_injection(text: str) -> bool:
    return bool(INJECTION_RE.search(text))


def ingest_document(store: Store, document_id: str) -> list[dict[str, Any]]:
    document = store.document(document_id)
    if not document:
        return []
    chunks: list[dict[str, Any]] = []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", document["content"]) if part.strip()]
    for index, paragraph in enumerate(paragraphs, start=1):
        section = paragraph.split(":", 1)[0] if ":" in paragraph else document["title"]
        chunks.append({
            "id": f"chk-{document_id}-{index}",
            "content": paragraph,
            "page": index,
            "section": section[:120],
            "keywords": sorted(tokens(paragraph)),
        })
    store.replace_chunks(document_id, document["workspace_id"], chunks)
    return chunks


def ensure_index(store: Store) -> None:
    for document in store.documents("demo-workspace"):
        if not store.chunks(document["workspace_id"]):
            ingest_document(store, document["id"])
            break
    # The first check above avoids unnecessary writes, while this handles a
    # partially-ingested database after a worker restart.
    indexed = {item["document_id"] for item in store.chunks("demo-workspace")}
    for document in store.documents("demo-workspace"):
        if document["id"] not in indexed:
            ingest_document(store, document["id"])


def visible(document: dict[str, Any], role: str) -> bool:
    if document["sensitivity"] == "public":
        return True
    return role in {"owner", "admin", "member"}


def query(store: Store, request: KnowledgeQuery) -> KnowledgeAnswer:
    if contains_injection(request.question):
        return KnowledgeAnswer(answer="I cannot follow instructions embedded in a request that try to override service-desk policies.", grounded=False, confidence=0.0, citations=[], warning="Prompt-injection attempt detected; routed to safe refusal.")
    candidates = []
    question_tokens = tokens(request.question)
    for chunk in store.chunks(request.workspace_id):
        document = store.document(chunk["document_id"])
        if not document or not visible(document, request.role):
            continue
        metadata = document.get("metadata", {})
        requested_model = (request.product_model or "").lower()
        models = [str(value).lower() for value in metadata.get("product_models", ["all"])]
        if requested_model and requested_model not in models:
            continue
        chunk_tokens = set(chunk["keywords"])
        overlap = question_tokens & chunk_tokens
        score = len(overlap) / max(len(question_tokens), 1)
        if score:
            candidates.append((score, chunk, document))
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = candidates[: request.top_k]
    rejected = [{"chunk_id": chunk["id"], "title": document["title"], "score": round(score, 3), "reason": "ranked below top_k"} for score, chunk, document in candidates[request.top_k : request.top_k + 3]]
    if not selected or selected[0][0] < 0.16:
        return KnowledgeAnswer(answer="I do not have enough approved evidence in the service-desk knowledge base to answer that safely. I have routed this for human review.", grounded=False, confidence=0.0 if not selected else round(selected[0][0], 3), citations=[], rejected_candidates=rejected, warning="Insufficient evidence")
    citations = [EvidenceCitation(document_id=document["id"], title=document["title"], page=chunk["page"], section=chunk["section"], chunk_id=chunk["id"], excerpt=chunk["content"], score=round(score, 3), source_url=document.get("source_url")) for score, chunk, document in selected]
    evidence = " ".join(f"{citation.excerpt}" for citation in citations[:3])
    answer = get_provider().grounded_answer(request.question, evidence, request.answer_mode)
    return KnowledgeAnswer(answer=answer, grounded=True, confidence=round(min(0.98, selected[0][0] + 0.35), 3), citations=citations, rejected_candidates=rejected)
