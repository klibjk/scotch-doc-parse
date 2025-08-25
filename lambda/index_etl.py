import json
import os
from typing import Any, Dict, List

import boto3
from botocore.config import Config

from common import chunking
from common import parse_document
from common.embeddings import embed_texts


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ETL Lambda: read uploaded doc from uploads bucket, parse, chunk, embed, and write JSONL.

    Supports direct invocation with {documentId, userId} or S3 ObjectCreated event.
    """
    s3 = boto3.client("s3", config=Config(retries={"max_attempts": 3}))
    uploads_bucket = os.environ.get("UPLOADS_BUCKET", "")
    index_bucket = os.environ.get("REPORTS_BUCKET", "")  # reuse reports bucket for now

    document_id = event.get("documentId")
    user_id = event.get("userId")
    s3_key: str | None = None

    # If called via S3 event, derive key and infer user/document
    if not document_id and isinstance(event.get("Records"), list):
        for rec in event["Records"]:
            try:
                if rec.get("eventSource") == "aws:s3":
                    bucket_name = rec.get("s3", {}).get("bucket", {}).get("name")
                    if bucket_name != uploads_bucket:
                        continue
                    k = rec.get("s3", {}).get("object", {}).get("key")
                    if isinstance(k, str) and (k.endswith(".pdf") or k.endswith(".xlsx")):
                        s3_key = k
                        break
            except Exception:
                continue
        if s3_key:
            # key format: userId/documentId.ext
            parts = s3_key.split("/")
            if len(parts) >= 2:
                user_id = user_id or parts[0]
                base = parts[-1]
                document_id = base.rsplit(".", 1)[0]

    if not document_id:
        return {"statusCode": 400, "body": json.dumps({"message": "documentId is required"})}
    if not user_id:
        user_id = "anon"

    # Locate object by extension
    key_pdf = f"{user_id}/{document_id}.pdf"
    key_xlsx = f"{user_id}/{document_id}.xlsx"

    obj = None
    key_used = None
    for key in (s3_key, key_pdf, key_xlsx):
        if not key:
            continue
        try:
            obj = s3.get_object(Bucket=uploads_bucket, Key=key)
            key_used = key
            break
        except Exception:
            continue
    if obj is None or key_used is None:
        return {"statusCode": 404, "body": json.dumps({"message": "document not found"})}

    data = obj["Body"].read()
    if key_used.endswith(".pdf"):
        parsed = parse_document.parse_pdf_bytes(data, filename=os.path.basename(key_used))
        chunks = chunking.chunk_pdf(parsed)
    else:
        parsed = parse_document.parse_xlsx_bytes(data, filename=os.path.basename(key_used))
        chunks = chunking.chunk_xlsx(parsed)

    # Persist normalized parsed JSON for memoization/zero-loss
    try:
        if index_bucket:
            raw_key = f"parsed/{user_id}/{document_id}.json"
            s3.put_object(
                Bucket=index_bucket,
                Key=raw_key,
                Body=json.dumps(parsed).encode("utf-8"),
                ContentType="application/json",
            )
    except Exception:
        pass

    texts = [c.get("text") or "" for c in chunks]
    vectors = embed_texts(texts)

    # Write JSONL with embeddings and metadata; path: embeddings/<userId>/<documentId>.jsonl
    lines: List[str] = []
    for c, v in zip(chunks, vectors):
        rec = {
            "documentId": document_id,
            "userId": user_id,
            "text": c.get("text"),
            "metadata": c.get("metadata") or {},
            "embedding": v,
        }
        lines.append(json.dumps(rec))
    body = ("\n").join(lines).encode("utf-8")
    out_key = f"embeddings/{user_id}/{document_id}.jsonl"
    s3.put_object(Bucket=index_bucket, Key=out_key, Body=body, ContentType="application/json")

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "indexed",
                "embeddings": f"s3://{index_bucket}/{out_key}",
                "parsed": f"s3://{index_bucket}/parsed/{user_id}/{document_id}.json",
                "chunks": len(chunks),
            }
        ),
    }
