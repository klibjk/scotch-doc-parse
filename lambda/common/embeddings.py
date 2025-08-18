from __future__ import annotations

from typing import List
import os
import boto3
from botocore.config import Config


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Compute embeddings for a list of texts using Bedrock (Titan or similar).

    Uses env BEDROCK_EMBEDDINGS_MODEL_ID. Falls back to trivial vectors if missing.
    """
    model_id = os.environ.get("BEDROCK_EMBEDDINGS_MODEL_ID")
    if not model_id:
        # Simple fallback: fixed-size zero vectors with length 8
        return [[0.0] * 8 for _ in texts]
    brt = boto3.client("bedrock-runtime", config=Config(retries={"max_attempts": 3}))
    vectors: List[List[float]] = []
    # Batch simply to avoid very large payloads; optimize as needed
    batch_size = 16
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        payload = {"inputText": batch}
        try:
            resp = brt.invoke_model(
                modelId=model_id,
                body=bytes(str(payload), "utf-8"),
                accept="application/json",
                contentType="application/json",
            )
            body = resp.get("body")
            data = body.read() if hasattr(body, "read") else body
            # Defer JSON parsing details; expect { "embeddings": [[...],[...], ...] }
            # To avoid strict dependency on response shape differences, do a light parse
            import json  # local import to avoid cold start cost until needed

            parsed = json.loads(data)
            vecs = parsed.get("embeddings") or parsed.get("vectors") or []
            if isinstance(vecs, list):
                for v in vecs:
                    if isinstance(v, list):
                        vectors.append([float(x) for x in v])
        except Exception:
            vectors.extend([[0.0] * 8 for _ in batch])
    # Ensure 1:1 length
    while len(vectors) < len(texts):
        vectors.append([0.0] * (len(vectors[0]) if vectors else 8))
    return vectors


