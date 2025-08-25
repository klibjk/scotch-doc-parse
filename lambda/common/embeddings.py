from __future__ import annotations

from typing import List
import os
import json
import boto3
from botocore.config import Config


def _parse_titan_response(payload: bytes | str) -> list[list[float]]:
    try:
        data = json.loads(
            payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        )
    except Exception:
        return []
    # Titan v2 batched: { "embeddings": [ { "embedding": [...] }, ... ] }
    if isinstance(data, dict):
        embs = data.get("embeddings")
        if isinstance(embs, list):
            out: list[list[float]] = []
            for item in embs:
                vec = None
                if isinstance(item, dict):
                    vec = item.get("embedding") or item.get("vector")
                elif isinstance(item, list):
                    vec = item
                if isinstance(vec, list):
                    out.append([float(x) for x in vec])
            if out:
                return out
        # Single input: { "embedding": [...] }
        vec = data.get("embedding") or data.get("vector")
        if isinstance(vec, list):
            return [[float(x) for x in vec]]
    return []


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Compute embeddings using Bedrock text-embeddings model (e.g., amazon.titan-embed-text-v2:0).

    Returns one vector per input text. Falls back to small zero vectors if unavailable.
    """
    model_id = os.environ.get("BEDROCK_EMBEDDINGS_MODEL_ID")
    if not model_id:
        return [[0.0] * 8 for _ in texts]

    brt = boto3.client("bedrock-runtime", config=Config(retries={"max_attempts": 3}))
    vectors: List[List[float]] = []
    for text in texts:
        body = json.dumps({"inputText": text}).encode("utf-8")
        vec: List[float] | None = None
        try:
            resp = brt.invoke_model(
                modelId=model_id,
                body=body,
                accept="application/json",
                contentType="application/json",
            )
            stream = resp.get("body")
            payload = stream.read() if hasattr(stream, "read") else stream
            parsed = _parse_titan_response(payload)
            if parsed and isinstance(parsed, list) and parsed[0]:
                vec = parsed[0]
        except Exception:
            vec = None
        vectors.append(vec if vec else [0.0] * 8)

    # Ensure 1:1 and at least some dimensionality
    if not vectors:
        return [[0.0] * 8 for _ in texts]
    return vectors
