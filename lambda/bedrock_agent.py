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

    # Compose an answer grounded on parsed docs: include excerpts
    excerpts = []
    for doc in parsed_docs:
        parsed = doc.get("parsed", {})
        text = parsed.get("text") or ""
        if not text and isinstance(parsed.get("pages"), list) and parsed["pages"]:
            # fallback to first page text
            first_page = parsed["pages"][0] or {}
            text = first_page.get("text") or ""
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
