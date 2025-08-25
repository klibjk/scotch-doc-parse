from __future__ import annotations

from typing import Any, Dict, Iterable, List
import csv
import io


def _split_text_with_overlap(text: str, max_chars: int, overlap: int) -> List[str]:
    if max_chars <= 0:
        return [text]
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def chunk_pdf(
    parsed: Dict[str, Any], max_chars: int = 4000, overlap: int = 400
) -> List[Dict[str, Any]]:
    """Create text-centric chunks from a parsed PDF structure.

    This is a character-based approximation to keep tokens under control without external tokenizers.
    Each chunk includes minimal metadata for later retrieval and citation.
    """
    chunks: List[Dict[str, Any]] = []
    pages = parsed.get("pages") or []
    metadata = parsed.get("metadata") or {}
    title = metadata.get("title")

    # Prefer per-page text to preserve page numbers for citations
    for page in pages:
        page_num = page.get("pageNumber") or page.get("page") or None
        page_text = page.get("text") or ""
        if not page_text:
            continue
        for piece in _split_text_with_overlap(page_text, max_chars=max_chars, overlap=overlap):
            if not piece.strip():
                continue
            chunks.append(
                {
                    "text": piece,
                    "metadata": {
                        "docType": "pdf",
                        "title": title,
                        "page": page_num,
                    },
                }
            )
    # Fallback: if no pages, chunk top-level text
    if not chunks:
        text = parsed.get("text") or ""
        for piece in _split_text_with_overlap(text, max_chars=max_chars, overlap=overlap):
            if not piece.strip():
                continue
            chunks.append(
                {
                    "text": piece,
                    "metadata": {"docType": "pdf", "title": title},
                }
            )
    return chunks


def chunk_xlsx(parsed: Dict[str, Any], rows_per_chunk: int = 1) -> List[Dict[str, Any]]:
    """Create row-group chunks from a parsed XLSX structure.

    Expects parsed["tables"] with optional sheet names and row arrays.
    """
    chunks: List[Dict[str, Any]] = []
    tables = parsed.get("tables") or []
    metadata = parsed.get("metadata") or {}
    title = metadata.get("title")
    for table in tables:
        sheet = table.get("name") or table.get("sheet")
        rows: List[Any] = table.get("rows") or []
        if not rows:
            # If no structured rows, fall back to table text
            table_text = table.get("text") or ""
            if table_text:
                chunks.append(
                    {
                        "text": table_text,
                        "metadata": {"docType": "xlsx", "title": title, "sheet": sheet},
                    }
                )
            continue
        # Determine header row (first non-empty row)
        headers: List[str] = []
        for hdr in rows[:3]:
            if isinstance(hdr, list) and any(str(x).strip() for x in hdr):
                headers = [str(h).strip() or f"col{idx+1}" for idx, h in enumerate(hdr)]
                break
        start_idx = 1 if headers else 0
        for idx in range(start_idx, len(rows)):
            row = rows[idx]
            if not isinstance(row, list):
                row = [row]
            col_map: Dict[str, Any] = {}
            for j, val in enumerate(row):
                key = headers[j] if j < len(headers) else f"col{j+1}"
                col_map[key] = val
            # Build compact text "key: value; ..." for retrieval
            text_pairs = "; ".join(f"{k}: {col_map[k]}" for k in col_map)
            chunks.append(
                {
                    "text": text_pairs,
                    "metadata": {
                        "docType": "xlsx",
                        "title": title,
                        "sheet": sheet,
                        "row": idx + 1,
                        "columns": col_map,
                    },
                }
            )
    # If no chunks were produced from top-level tables, try page-level items
    if not chunks:
        pages = parsed.get("pages") or []
        for page in pages:
            items = page.get("items") or []
            for it in items:
                # Handle shapes: { type: 'table', rows|csv|name } OR { table: { rows|csv|name } }
                table_obj = None
                if isinstance(it, dict):
                    if it.get("type") == "table":
                        table_obj = it
                    elif isinstance(it.get("table"), dict):
                        table_obj = it.get("table")
                if not isinstance(table_obj, dict):
                    continue
                sheet = table_obj.get("name") or table_obj.get("sheet") or page.get("name")
                rows = table_obj.get("rows") or []
                if not rows:
                    # Try parsing CSV if provided
                    csv_text = table_obj.get("csv") or ""
                    if isinstance(csv_text, str) and csv_text.strip():
                        try:
                            reader = csv.reader(io.StringIO(csv_text))
                            rows = [list(r) for r in reader]
                        except Exception:
                            rows = []
                if not rows:
                    # Last resort: flatten markdown text if present
                    md_text = table_obj.get("md") or table_obj.get("text") or ""
                    if isinstance(md_text, str) and md_text.strip():
                        chunks.append(
                            {
                                "text": md_text,
                                "metadata": {"docType": "xlsx", "title": title, "sheet": sheet},
                            }
                        )
                        continue
                # Determine header row (first non-empty row)
                headers: List[str] = []
                for hdr in rows[:3]:
                    if isinstance(hdr, list) and any(str(x).strip() for x in hdr):
                        headers = [str(h).strip() or f"col{idx+1}" for idx, h in enumerate(hdr)]
                        break
                start_idx = 1 if headers else 0
                for idx in range(start_idx, len(rows)):
                    row = rows[idx]
                    if not isinstance(row, list):
                        row = [row]
                    col_map: Dict[str, Any] = {}
                    for j, val in enumerate(row):
                        key = headers[j] if j < len(headers) else f"col{j+1}"
                        col_map[key] = val
                    text_pairs = "; ".join(f"{k}: {col_map[k]}" for k in col_map)
                    chunks.append(
                        {
                            "text": text_pairs,
                            "metadata": {
                                "docType": "xlsx",
                                "title": title,
                                "sheet": sheet,
                                "row": idx + 1,
                                "columns": col_map,
                            },
                        }
                    )
    return chunks
