import os
import json
from typing import Dict, Any
import urllib.request
import urllib.error
import base64
import boto3

LLAMAPARSE_API_KEY_ENV = "LLAMAPARSE_API_KEY"
LLAMAPARSE_SECRET_ID_ENV = "LLAMAPARSE_SECRET_ID"
LLAMAPARSE_API_URL_ENV = "LLAMAPARSE_API_URL"  # e.g., https://api.llamaparse.com/v1/parse

_secrets_client = boto3.client("secretsmanager")


def _get_llamaparse_api_key() -> str | None:
    # Priority: explicit env key, then Secrets Manager by ID
    key = os.getenv(LLAMAPARSE_API_KEY_ENV)
    if key:
        return key
    secret_id = os.getenv(LLAMAPARSE_SECRET_ID_ENV)
    if not secret_id:
        return None
    try:
        resp = _secrets_client.get_secret_value(SecretId=secret_id)
        sec = resp.get("SecretString") or base64.b64decode(resp.get("SecretBinary") or b"").decode("utf-8")
        # Allow both raw key or JSON {"api_key": "..."}
        try:
            data = json.loads(sec)
            return data.get("api_key") or data.get("LLAMAPARSE_API_KEY") or sec
        except Exception:
            return sec
    except Exception:
        return None


def parse_pdf_bytes(pdf_bytes: bytes, filename: str = "document.pdf") -> Dict[str, Any]:
    """Calls LlamaParse if configured, otherwise returns a stubbed parse."""
    api_url = os.getenv(LLAMAPARSE_API_URL_ENV)
    api_key = _get_llamaparse_api_key()
    if api_url and api_key:
        try:
            req = urllib.request.Request(api_url, method="POST")
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("Content-Type", "application/pdf")
            # Some APIs require filename; include as header if supported
            req.add_header("X-Filename", filename)
            with urllib.request.urlopen(req, data=pdf_bytes, timeout=60) as resp:
                data = resp.read()
                parsed = json.loads(data)
                # Attempt to normalize keys; otherwise, wrap raw
                normalized = {
                    "text": parsed.get("text") or "",
                    "pages": parsed.get("pages") or [],
                    "tables": parsed.get("tables") or [],
                    "metadata": parsed.get("metadata") or {"title": filename},
                }
                return normalized
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            # fall back to stub on failure
            pass

    # Stub fallback
    return {
        "text": f"Parsed content for {filename} (stub)",
        "pages": [{"pageNumber": 1, "text": "Example page text (stub)"}],
        "tables": [],
        "metadata": {"title": filename},
    }
