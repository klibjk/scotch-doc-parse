from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import boto3
from botocore.config import Config

from .embeddings import embed_texts


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    # Ensure same length
    n = min(len(a), len(b))
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        va = float(a[i])
        vb = float(b[i])
        dot += va * vb
        na += va * va
        nb += vb * vb
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / ((na**0.5) * (nb**0.5))


def retrieve_top_k(
    prompt: str,
    user_id: str,
    document_ids: List[str],
    reports_bucket: str,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Load embeddings JSONL for the given documents and return top-k chunks by similarity.

    Returns list of { documentId, text, metadata, score } sorted by score desc.
    """
    if not prompt or not document_ids:
        return []

    s3 = boto3.client("s3", config=Config(retries={"max_attempts": 3}))
    # Embed the prompt once
    q_vecs = embed_texts([prompt])
    if not q_vecs:
        return []
    q_vec = q_vecs[0]

    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for doc_id in document_ids:
        key = f"embeddings/{user_id}/{doc_id}.jsonl"
        try:
            obj = s3.get_object(Bucket=reports_bucket, Key=key)
            body = obj["Body"].read()
        except Exception:
            continue
        for line in body.splitlines():
            try:
                rec = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            vec = rec.get("embedding") or []
            score = _cosine_similarity(q_vec, vec)
            candidates.append((score, rec))

    if not candidates:
        return []
    # Prefer rows whose Topic matches product/entity terms in the question
    q = (prompt or "").lower()
    q_terms = [t for t in q.replace("?", " ").replace(",", " ").split() if len(t) > 2]
    def topic_of(rec: Dict[str, Any]) -> str:
        meta = rec.get("metadata") or {}
        cols = meta.get("columns") or {}
        if isinstance(cols, dict):
            # try 'Topic' key case-insensitively
            for k, v in cols.items():
                if str(k).strip().lower() == "topic":
                    return str(v or "").lower()
        return ""
    filtered: List[Tuple[float, Dict[str, Any]]] = []
    for s, r in candidates:
        top = topic_of(r)
        if top and any(term in top for term in q_terms):
            filtered.append((s, r))
    # Only apply filter if it yields results
    if filtered:
        candidates = filtered
    # If all embedding scores are ~0, apply lexical scoring fallback (still strict retrieval)
    max_score = max(s for s, _ in candidates)
    if max_score <= 1e-9:
        q = (prompt or "").lower()
        # basic tokenization
        terms = [t for t in q.replace("?", " ").replace(",", " ").split() if len(t) > 2]

        def lex_score(txt: str) -> int:
            lt = (txt or "").lower()
            return sum(lt.count(t) for t in terms)

        lex_scored = []
        for _, rec in candidates:
            s = lex_score(rec.get("text") or "")
            lex_scored.append((s, rec))
        # filter to those with at least one hit
        lex_scored = [x for x in lex_scored if x[0] > 0]
        if lex_scored:
            lex_scored.sort(key=lambda x: x[0], reverse=True)
            top = lex_scored[:top_k]
            return [
                {
                    "documentId": r.get("documentId"),
                    "text": r.get("text") or "",
                    "metadata": r.get("metadata") or {},
                    "score": s,
                }
                for s, r in top
            ]
        # If still nothing, fall through to return arbitrary top_k by cosine (all zeros)
    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:top_k]
    return [
        {
            "documentId": r.get("documentId"),
            "text": r.get("text") or "",
            "metadata": r.get("metadata") or {},
            "score": score,
        }
        for score, r in top
    ]
