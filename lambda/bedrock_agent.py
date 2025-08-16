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
        # We won't actually fetch; just construct an S3 URL key for the stub
        object_url = f"s3://{uploads_bucket}/{key}"
        parsed = llama_parse.parse_pdf_from_s3_object_url(object_url)
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
