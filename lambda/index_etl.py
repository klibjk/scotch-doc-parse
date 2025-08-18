import json
import os
from typing import Any, Dict, List

import boto3
from botocore.config import Config

from common import chunking
from common import parse_document
from common.embeddings import embed_texts


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """ETL Lambda: read uploaded doc from uploads bucket, parse, chunk, embed, and write JSONL."""
    s3 = boto3.client("s3", config=Config(retries={"max_attempts": 3}))
    uploads_bucket = os.environ.get("UPLOADS_BUCKET", "")
    index_bucket = os.environ.get("REPORTS_BUCKET", "")  # reuse reports bucket for now

    document_id = event.get("documentId")
    user_id = event.get("userId", "anon")
    if not document_id:
        return {"statusCode": 400, "body": json.dumps({"message": "documentId is required"})}

    # Locate object by extension
    key_pdf = f"{user_id}/{document_id}.pdf"
    key_xlsx = f"{user_id}/{document_id}.xlsx"

    obj = None
    key_used = None
    for key in (key_pdf, key_xlsx):
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
        "body": json.dumps({"message": "indexed", "s3": f"s3://{index_bucket}/{out_key}", "chunks": len(chunks)}),
    }


