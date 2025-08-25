from __future__ import annotations

from typing import Any, Dict, Iterable, List


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


def chunk_xlsx(parsed: Dict[str, Any], rows_per_chunk: int = 50) -> List[Dict[str, Any]]:
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
        i = 0
        while i < len(rows):
            group = rows[i : i + rows_per_chunk]
            # Serialize small row-groups to compact TSV-like text for embeddings
            text_lines: List[str] = []
            for row in group:
                if isinstance(row, list):
                    text_lines.append("\t".join(str(c) for c in row))
                else:
                    text_lines.append(str(row))
            chunk_text = "\n".join(text_lines)
            chunks.append(
                {
                    "text": chunk_text,
                    "metadata": {
                        "docType": "xlsx",
                        "title": title,
                        "sheet": sheet,
                        "rowStart": i + 1,
                        "rowEnd": min(i + rows_per_chunk, len(rows)),
                    },
                }
            )
            i += rows_per_chunk
    return chunks
