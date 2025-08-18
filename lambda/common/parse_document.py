from __future__ import annotations

from typing import Any, Dict, List

from . import llama_parse


def parse_pdf_bytes(pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    parsed = llama_parse.parse_pdf_bytes(pdf_bytes, filename=filename)
    # Preserve full structure: text, pages, and tables from LlamaParse
    text = parsed.get("text") or ""
    if not text and isinstance(parsed.get("pages"), list) and parsed["pages"]:
        first_page = parsed["pages"][0] or {}
        text = first_page.get("text") or ""
    normalized: Dict[str, Any] = {
        "docType": "pdf",
        "text": text or "",
        "pages": parsed.get("pages") or [],
        "tables": parsed.get("tables") or [],
        "metadata": parsed.get("metadata", {}),
    }
    return normalized


def parse_xlsx_bytes(xlsx_bytes: bytes, filename: str) -> Dict[str, Any]:
    # Delegate to LlamaParse's XLSX support
    result = llama_parse.parse_xlsx_bytes(xlsx_bytes, filename=filename)
    # Normalize to common structure
    text = result.get("text") or ""
    tables = result.get("tables") or []
    metadata = result.get("metadata") or {"title": filename}
    return {
        "docType": "xlsx",
        "text": text,
        "pages": result.get("pages") or [],
        "tables": tables,
        "metadata": metadata,
    }


