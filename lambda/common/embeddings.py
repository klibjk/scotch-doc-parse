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
    batch_size = 16
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        body = json.dumps({"inputText": batch}).encode("utf-8")
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
            if parsed:
                vectors.extend(parsed)
                continue
        except Exception:
            pass
        # On failure or empty parse, append zeros for the batch
        vectors.extend([[0.0] * 8 for _ in batch])

    # Ensure 1:1 result length
    if len(vectors) != len(texts):
        # Pad or truncate conservatively
        if len(vectors) < len(texts):
            pad_len = len(texts) - len(vectors)
            vectors.extend([[0.0] * (len(vectors[0]) if vectors else 8) for _ in range(pad_len)])
        else:
            vectors = vectors[: len(texts)]
    return vectors
