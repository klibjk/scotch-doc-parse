import json
import os
import time
import re
from typing import Any, Dict, List
import boto3
from botocore.config import Config
from common import parse_document
from common.retrieval import retrieve_top_k


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # Placeholder that returns a deterministic fake result for now
    prompt = event.get("prompt") if isinstance(event, dict) else None
    mode = (event.get("mode") or "retrieval").lower()
    document_ids: List[str] = event.get("documentIds") or []

    s3 = boto3.client("s3", config=Config(retries={"max_attempts": 3}))
    uploads_bucket = os.environ.get("UPLOADS_BUCKET", "")
    reports_bucket = os.environ.get("REPORTS_BUCKET", "")

    parsed_docs = []
    sources = []
    doc_id_to_filename: Dict[str, str] = {}
    for doc_id in document_ids:
        # Try both pdf and xlsx keys to locate the uploaded object
        user_prefix = event.get("userId", "anon")
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
            if key_used.endswith(".pdf"):
                # Prefer original filename from S3 metadata if present
                original_filename = (obj.get("Metadata") or {}).get(
                    "original-filename"
                ) or os.path.basename(key_used)
                parsed = parse_document.parse_pdf_bytes(data, filename=original_filename)
            elif key_used.endswith(".xlsx"):
                try:
                    original_filename = (obj.get("Metadata") or {}).get(
                        "original-filename"
                    ) or os.path.basename(key_used)
                    parsed = parse_document.parse_xlsx_bytes(data, filename=original_filename)
                except Exception:
                    parsed = {
                        "docType": "xlsx",
                        "text": "",
                        "tables": [],
                        "metadata": {"error": "xlsx parse failed"},
                    }
            else:
                parsed = {"docType": "unknown", "text": "", "tables": [], "metadata": {}}
        else:
            parsed = {
                "docType": "missing",
                "text": "",
                "tables": [],
                "metadata": {"error": "object not found"},
            }
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

        filename_only = (
            (obj.get("Metadata") or {}).get("original-filename") if obj is not None else ""
        ) or (os.path.basename(key_used) if key_used else "")
        if filename_only:
            doc_id_to_filename[doc_id] = filename_only
        parsed_docs.append({"documentId": doc_id, "parsed": parsed})
        sources.append({"documentId": doc_id, "filename": filename_only, "pages": [1]})

    # Try vector retrieval first (if embeddings exist), fall back to raw excerpts
    reports_bucket = os.environ.get("REPORTS_BUCKET", "")
    retrieved = []
    if mode == "retrieval" and reports_bucket and document_ids and prompt:
        try:
            retrieved = retrieve_top_k(
                prompt=prompt,
                user_id=event.get("userId", "anon"),
                document_ids=document_ids,
                reports_bucket=reports_bucket,
                top_k=5,
            )
        except Exception:
            retrieved = []

    excerpts: list[str] = []
    if retrieved:
        # If the prompt asks for a specific page (e.g., "page 3"), bias to that page
        try:
            m = re.search(r"\bpage\s+(\d+)\b", (prompt or ""), re.IGNORECASE)
            if m:
                page_num = int(m.group(1))
                filt = [r for r in retrieved if (r.get("metadata") or {}).get("page") == page_num]
                if filt:
                    retrieved = filt
        except Exception:
            pass
        # Lightweight keyword filter to prefer chunks that actually contain request terms
        try:
            q = (prompt or "").lower()
            key_terms = set()
            for token in [
                "experience",
                "years",
                "requirement",
                "qualification",
                "responsibilit",
                "skills",
            ]:
                if token in q:
                    key_terms.add(token)
            if key_terms:

                def has_terms(txt: str) -> bool:
                    lt = txt.lower()
                    return (
                        any(t in lt for t in key_terms)
                        or bool(re.search(r"\b\d{1,2}\s*(?:years|yrs)\b", lt))
                        or bool(re.search(r"\b\d{1,2}\s*[-–]\s*\d{1,2}\b", lt))
                    )

                filtered = [r for r in retrieved if has_terms(r.get("text") or "")]
                if filtered:
                    retrieved = filtered
        except Exception:
            pass
        for r in retrieved:
            txt = r.get("text") or ""
            meta = r.get("metadata") or {}
            cite = []
            if "page" in meta:
                cite.append(f"p.{meta['page']}")
            if "sheet" in meta:
                cite.append(f"sheet {meta['sheet']}")
            cite_suffix = f" ({' ,'.join(cite)})" if cite else ""
            if txt:
                excerpts.append((txt.strip() + cite_suffix)[:1200])
        # Build sources from retrieved hits
        sources = []
        for r in retrieved:
            meta = r.get("metadata") or {}
            doc_id_r = r.get("documentId")
            src = {
                "documentId": doc_id_r,
                "filename": doc_id_to_filename.get(str(doc_id_r), ""),
                "pages": [],
            }
            if "page" in meta and isinstance(meta["page"], int):
                src["pages"].append(meta["page"])
            sources.append(src)
    else:
        # Baseline: Build previews from parsed pages with simple relevance scoring
        try:
            q = (prompt or "").lower()
            m = re.search(r"\bpage\s+(\d+)\b", q, re.IGNORECASE)
            requested_page = int(m.group(1)) if m else None
        except Exception:
            requested_page = None

        def page_score(page_text: str) -> int:
            score = 0
            lt = page_text.lower()
            for term in [
                "experience",
                "years",
                "requirement",
                "qualification",
                "responsibilit",
                "skills",
            ]:
                score += lt.count(term)
            if re.search(r"\b\d{1,2}\s*(?:years|yrs)\b", lt) or re.search(
                r"\b\d{1,2}\s*[-–]\s*\d{1,2}\b", lt
            ):
                score += 3
            return score

        selected_sources: list[Dict[str, Any]] = []
        for doc in parsed_docs:
            doc_id = doc.get("documentId")
            parsed = doc.get("parsed", {})
            pages = parsed.get("pages") or []
            filename = doc_id_to_filename.get(str(doc_id), "")
            chosen_pages: list[int] = []
            if requested_page:
                for p in pages:
                    if int(p.get("page") or p.get("pageNumber") or 0) == requested_page:
                        chosen_pages = [requested_page]
                        excerpts.append((p.get("text") or "").strip()[:1200])
                        break
            if not chosen_pages:
                scored = []
                for p in pages:
                    pn = int(p.get("page") or p.get("pageNumber") or 0)
                    txt = p.get("text") or ""
                    scored.append((page_score(txt), pn, txt))
                # Pick top 2 pages with score > 0, else fall back to first page
                scored.sort(key=lambda x: x[0], reverse=True)
                picks = [s for s in scored if s[0] > 0][:2]
                if not picks and scored:
                    picks = scored[:1]
                for _, pn, txt in picks:
                    if txt:
                        excerpts.append(txt.strip()[:1200])
                        chosen_pages.append(pn)
            selected_sources.append(
                {"documentId": doc_id, "filename": filename, "pages": chosen_pages}
            )
        # Replace sources only with selected pages (avoid showing all pages)
        sources = selected_sources

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
                    messages=[{"role": "user", "content": [{"text": content_text}]}],
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
        joined_titles = ", ".join(
            [
                p["parsed"].get("metadata", {}).get("title", doc.get("documentId"))
                for doc in parsed_docs
                for p in [doc]
            ]
        )
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
