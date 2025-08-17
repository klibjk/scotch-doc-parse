import os
import json
from typing import Dict, Any, Optional
import urllib.request
import urllib.error
import base64
import time
import uuid
import boto3

LLAMAPARSE_API_KEY_ENV = "LLAMAPARSE_API_KEY"
LLAMAPARSE_SECRET_ID_ENV = "LLAMAPARSE_SECRET_ID"
# Base URL of Llama Cloud Parsing API. Defaults to official endpoint.
LLAMAPARSE_BASE_URL_ENV = "LLAMAPARSE_BASE_URL"  # e.g., https://api.cloud.llamaindex.ai/api/v1

_secrets_client = boto3.client("secretsmanager")


def _get_llamaparse_api_key() -> Optional[str]:
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


def _multipart_form(file_bytes: bytes, filename: str, content_type: str = "application/pdf") -> (bytes, str):
    boundary = f"--------------------------{uuid.uuid4().hex}"
    lines = []
    lines.append(f"--{boundary}\r\n".encode("utf-8"))
    lines.append(
        (
            f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    lines.append(file_bytes)
    lines.append("\r\n".encode("utf-8"))
    lines.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(lines)
    content_type_header = f"multipart/form-data; boundary={boundary}"
    return body, content_type_header


def _http_request(url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None, data: Optional[bytes] = None, timeout: int = 60) -> (int, bytes):
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
        return resp.getcode(), resp.read()


def _normalize_result(json_result: Dict[str, Any], text_fallback: Optional[str], filename: str) -> Dict[str, Any]:
    text = text_fallback or json_result.get("text") or ""
    pages = json_result.get("pages") or []
    tables = json_result.get("tables") or []
    metadata = json_result.get("metadata") or {"title": filename}
    return {"text": text, "pages": pages, "tables": tables, "metadata": metadata}


def parse_pdf_bytes(pdf_bytes: bytes, filename: str = "document.pdf") -> Dict[str, Any]:
    """Implements Llama Cloud job-based Parsing API flow:
    1) POST multipart to /parsing/upload -> returns job id
    2) Poll /parsing/job/<id> until SUCCESS
    3) GET /parsing/job/<id>/result/json and /result/text, then normalize

    If API key is missing or any step fails, returns a stub result.
    """
    api_key = _get_llamaparse_api_key()
    base_url = os.getenv(LLAMAPARSE_BASE_URL_ENV, "https://api.cloud.llamaindex.ai/api/v1").rstrip("/")
    if not api_key:
        return {
            "text": f"Parsed content for {filename} (stub)",
            "pages": [{"pageNumber": 1, "text": "Example page text (stub)"}],
            "tables": [],
            "metadata": {"title": filename},
        }

    try:
        # Step 1: upload
        upload_url = f"{base_url}/parsing/upload"
        body, content_type = _multipart_form(pdf_bytes, filename, content_type="application/pdf")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
        }
        status, data = _http_request(upload_url, method="POST", headers=headers, data=body, timeout=60)
        if status // 100 != 2:
            raise RuntimeError(f"Upload failed: HTTP {status}")
        upload_resp = json.loads(data)
        job_id = upload_resp.get("id") or upload_resp.get("job_id")
        if not job_id:
            raise RuntimeError("Upload response missing job id")

        # Step 2: poll status
        status_url = f"{base_url}/parsing/job/{job_id}"
        start_time = time.time()
        while True:
            st_code, st_data = _http_request(status_url, method="GET", headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            }, timeout=30)
            if st_code // 100 != 2:
                raise RuntimeError(f"Status check failed: HTTP {st_code}")
            st_json = json.loads(st_data)
            st = (st_json.get("status") or "").upper()
            if st in ("SUCCESS", "SUCCEEDED", "COMPLETED"):
                break
            if st in ("FAILED", "ERROR"):
                raise RuntimeError(f"Parsing job failed: {st_json}")
            if time.time() - start_time > 180:
                raise TimeoutError("Timeout waiting for LlamaParse job to complete")
            time.sleep(2.0)

        # Step 3: fetch results (json + optional text)
        result_json_url = f"{base_url}/parsing/job/{job_id}/result/json"
        rj_code, rj_data = _http_request(result_json_url, method="GET", headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }, timeout=60)
        rj_json = json.loads(rj_data) if rj_code // 100 == 2 else {}

        text_url = f"{base_url}/parsing/job/{job_id}/result/text"
        try:
            rt_code, rt_data = _http_request(text_url, method="GET", headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            }, timeout=60)
            text_json = json.loads(rt_data) if rt_code // 100 == 2 else {}
            text_value = text_json.get("text") if isinstance(text_json, dict) else None
        except Exception:
            text_value = None

        return _normalize_result(rj_json if isinstance(rj_json, dict) else {}, text_value, filename)

    except Exception:
        # Fallback stub on any failure
        return {
            "text": f"Parsed content for {filename} (stub)",
            "pages": [{"pageNumber": 1, "text": "Example page text (stub)"}],
            "tables": [],
            "metadata": {"title": filename},
        }
