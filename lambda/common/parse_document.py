from __future__ import annotations

from typing import Any, Dict, List

from . import llama_parse


def parse_pdf_bytes(pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    parsed = llama_parse.parse_pdf_bytes(pdf_bytes, filename=filename)
    text = parsed.get("text") or ""
    if not text and isinstance(parsed.get("pages"), list) and parsed["pages"]:
        first_page = parsed["pages"][0] or {}
        text = first_page.get("text") or ""
    normalized: Dict[str, Any] = {
        "docType": "pdf",
        "text": text or "",
        "tables": [],
        "metadata": parsed.get("metadata", {}),
    }
    return normalized


def parse_xlsx_bytes(xlsx_bytes: bytes, filename: str) -> Dict[str, Any]:
    import io
    import pandas as pd  # type: ignore

    buf = io.BytesIO(xlsx_bytes)
    sheets = pd.read_excel(buf, sheet_name=None, engine="openpyxl")
    tables: List[Dict[str, Any]] = []
    text_parts: List[str] = []
    for name, df in sheets.items():
        # Limit rows to keep payload small
        preview = df.head(50).copy()
        records = preview.fillna("").to_dict(orient="records")
        tables.append({"name": str(name), "rows": records})
        # Add a compact summary line
        cols = ", ".join(map(str, list(preview.columns)))
        text_parts.append(f"Sheet {name}: columns {cols} | {len(preview)} rows preview")
    normalized: Dict[str, Any] = {
        "docType": "xlsx",
        "text": "\n".join(text_parts),
        "tables": tables,
        "metadata": {"sheetNames": [t["name"] for t in tables]},
    }
    return normalized


