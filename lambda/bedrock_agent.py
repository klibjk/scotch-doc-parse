import json
import os
import time
from typing import Any, Dict, List
import boto3
from botocore.config import Config
from common import llama_parse


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # Placeholder that returns a deterministic fake result for now
    prompt = event.get("prompt") if isinstance(event, dict) else None
    document_ids: List[str] = event.get("documentIds") or []

    s3 = boto3.client("s3", config=Config(retries={"max_attempts": 3}))
    uploads_bucket = os.environ.get("UPLOADS_BUCKET", "")

    parsed_docs = []
    sources = []
    for doc_id in document_ids:
        key = f"{event.get('userId','anon')}/{doc_id}.pdf"
        # Download the first ~5MB (or full) to pass to LlamaParse client
        try:
            obj = s3.get_object(Bucket=uploads_bucket, Key=key)
            pdf_bytes = obj["Body"].read()
            parsed = llama_parse.parse_pdf_bytes(pdf_bytes, filename=f"{doc_id}.pdf")
        except Exception:
            parsed = llama_parse.parse_pdf_bytes(b"", filename=f"{doc_id}.pdf")
        parsed_docs.append({"documentId": doc_id, "parsed": parsed})
        sources.append({"documentId": doc_id, "pages": [1]})

    # Compose a naive response grounded on the parsed docs (stub behavior)
    joined_titles = ", ".join([p["parsed"]["metadata"].get("title", doc.get("documentId")) for doc in parsed_docs for p in [doc]])
    summary_text = f"Answer (stub) to: {prompt}. Parsed {len(parsed_docs)} document(s): {joined_titles}."
    result = {
        "text": summary_text,
        "sources": sources,
        "report": {"format": "markdown", "content": f"# Report\n\n{summary_text}"},
    }
    completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "agentResult": json.dumps(result),
        "completedAt": completed_at,
        "sessionId": event.get("sessionId", ""),
    }
