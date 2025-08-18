import os
import json
import importlib.util
from pathlib import Path

# Load module by file path to avoid package import issues
ROOT = Path(__file__).resolve().parents[1]
LLAMA_PARSE_PATH = ROOT / "lambda" / "common" / "llama_parse.py"
spec = importlib.util.spec_from_file_location("llama_parse", str(LLAMA_PARSE_PATH))
llama_parse = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
assert spec and spec.loader
spec.loader.exec_module(llama_parse)  # type: ignore[union-attr]


def summarize_result(name: str, result: dict) -> dict:
    text = result.get("text") or ""
    tables = result.get("tables") or []
    meta = result.get("metadata") or {}
    preview_rows = []
    for t in tables[:2]:  # first two tables
        rows = t.get("rows") or []
        preview_rows.append(
            {
                "name": t.get("name"),
                "rows": rows[:2],  # first two rows
            }
        )
    return {
        "doc": name,
        "metadata": meta,
        "text_len": len(text),
        "num_tables": len(tables),
        "tables_preview": preview_rows,
        "text_preview": text[:500],
    }


def main() -> None:
    # Allow using Secrets Manager via env var if not already set
    os.environ.setdefault("LLAMAPARSE_SECRET_ID", "/scotch-doc-parse/llamaparse")

    roots = [
        Path("sample_docs/Mock-SalesReport.xlsx"),
        Path("sample_docs/Technical Program Management Architect.pdf"),
    ]

    outputs = []
    for p in roots:
        if not p.exists():
            outputs.append({"doc": str(p), "error": "missing file"})
            continue
        data = p.read_bytes()
        if p.suffix.lower() == ".pdf":
            res = llama_parse.parse_pdf_bytes(data, filename=p.name)
        elif p.suffix.lower() == ".xlsx":
            res = llama_parse.parse_xlsx_bytes(data, filename=p.name)
        else:
            outputs.append({"doc": str(p), "error": f"unsupported type {p.suffix}"})
            continue
        outputs.append(summarize_result(p.name, res))

    print(json.dumps({"results": outputs}, indent=2))


if __name__ == "__main__":
    main()
