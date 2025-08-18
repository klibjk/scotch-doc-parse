import json
import os
import time
from typing import Any, Dict, List
import boto3
from botocore.config import Config
from common import parse_document


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # Placeholder that returns a deterministic fake result for now
    prompt = event.get("prompt") if isinstance(event, dict) else None
    document_ids: List[str] = event.get("documentIds") or []

    s3 = boto3.client("s3", config=Config(retries={"max_attempts": 3}))
    uploads_bucket = os.environ.get("UPLOADS_BUCKET", "")
    reports_bucket = os.environ.get("REPORTS_BUCKET", "")

    parsed_docs = []
    sources = []
    for doc_id in document_ids:
        # Try both pdf and xlsx keys to locate the uploaded object
        user_prefix = event.get('userId','anon')
        tried_keys = [
            f"{user_prefix}/{doc_id}.pdf",
            f"{user_prefix}/{doc_id}.xlsx",
        ]
        obj = None
        key_used = None
        for key in tried_keys:
            try:
                obj = s3.get_object(Bucket=uploads_bucket, Key=key)
                key_used = key
                break
            except Exception:
                continue
        parsed: Dict[str, Any]
        if obj is not None and key_used is not None:
            data = obj["Body"].read()
            if key_used.endswith('.pdf'):
                parsed = parse_document.parse_pdf_bytes(data, filename=os.path.basename(key_used))
            elif key_used.endswith('.xlsx'):
                try:
                    parsed = parse_document.parse_xlsx_bytes(data, filename=os.path.basename(key_used))
                except Exception:
                    parsed = {"docType": "xlsx", "text": "", "tables": [], "metadata": {"error": "xlsx parse failed"}}
            else:
                parsed = {"docType": "unknown", "text": "", "tables": [], "metadata": {}}
        else:
            parsed = {"docType": "missing", "text": "", "tables": [], "metadata": {"error": "object not found"}}
        # Persist parsed JSON to S3 for zero-loss preservation and attach pointer
        try:
            if reports_bucket:
                raw_key = f"parsed/{user_prefix}/{doc_id}.json"
                s3.put_object(
                    Bucket=reports_bucket,
                    Key=raw_key,
                    Body=json.dumps(parsed).encode("utf-8"),
                    ContentType="application/json",
                )
                meta = parsed.get("metadata") or {}
                meta["rawS3Uri"] = f"s3://{reports_bucket}/{raw_key}"
                parsed["metadata"] = meta
        except Exception:
            # Non-fatal: continue without raw pointer if write fails
            pass

        parsed_docs.append({"documentId": doc_id, "parsed": parsed})
        sources.append({"documentId": doc_id, "pages": [1]})

    # Compose an answer grounded on parsed docs: include excerpts
    excerpts = []
    for doc in parsed_docs:
        parsed = doc.get("parsed", {})
        text = parsed.get("text") or ""
        if text:
            excerpts.append(text.strip())

    if excerpts:
        # Limit to a reasonable preview length
        preview = ("\n\n---\n\n").join(excerpts)[:2000]
        # Call Bedrock Runtime directly with prompt + parsed context. Then fallback to excerpts.
        answer_text = None
        bedrock_model_id = os.environ.get("BEDROCK_MODEL_ID")
        if bedrock_model_id:
            try:
                brt = boto3.client("bedrock-runtime", config=Config(retries={"max_attempts": 3}))
                system_inst = (
                    "You are a document analysis assistant. Answer the user's question using ONLY the provided parsed content. "
                    "Be concise and include a short Sources section with documentId and page numbers if possible."
                )
                content_text = (
                    f"Question: {prompt}\n\n"
                    f"Parsed content excerpt (may be truncated):\n{preview}"
                )
                resp = brt.converse(
                    modelId=bedrock_model_id,
                    messages=[
                        {"role": "user", "content": [{"text": content_text}]}
                    ],
                    system=[{"text": system_inst}],
                )
                parts = resp.get("output", {}).get("message", {}).get("content", [])
                if parts:
                    answer_text = parts[0].get("text") or ""
            except Exception:
                answer_text = None
        if not answer_text:
            answer_text = f"Here is an excerpt based on your question: '{prompt}'.\n\n" + preview
        report_md = f"# Report\n\n## Prompt\n{prompt}\n\n## Excerpts\n\n{preview}\n"
    else:
        joined_titles = ", ".join([
            p["parsed"].get("metadata", {}).get("title", doc.get("documentId"))
            for doc in parsed_docs for p in [doc]
        ])
        answer_text = (
            f"No parsed text extracted. Parsed {len(parsed_docs)} document(s): {joined_titles}."
        )
        report_md = f"# Report\n\n{answer_text}\n"

    result = {
        "text": answer_text,
        "sources": sources,
        "report": {"format": "markdown", "content": report_md},
    }
    completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "agentResult": json.dumps(result),
        "completedAt": completed_at,
        "sessionId": event.get("sessionId", ""),
    }
