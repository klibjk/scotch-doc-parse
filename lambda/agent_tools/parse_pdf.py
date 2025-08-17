import json
import os
import boto3
from botocore.config import Config
from typing import Any, Dict
from common import llama_parse

s3 = boto3.client("s3", config=Config(retries={"max_attempts": 3}))
UPLOADS_BUCKET = os.environ.get("UPLOADS_BUCKET", "")


def _ok_response(action_group: str, function: str, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "function": function,
            "functionResponse": {
                "responseBody": {
                    "application/json": {
                        "body": body
                    }
                }
            }
        }
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # Expecting Bedrock Agent action group event (OpenAPI based)
    # Extract request JSON
    try:
        request = event.get("requestBody") or {}
        if isinstance(request, dict) and "content" in request:
            # Some payloads nest under content -> application/json -> body
            content = request.get("content", {}).get("application/json", {})
            payload = content.get("body") or {}
        else:
            payload = request if isinstance(request, dict) else {}
        document_id = payload.get("documentId")
        user_id = payload.get("userId") or "anon"
        if not document_id:
            return _ok_response(event.get("actionGroup", "DocParseTools"), event.get("function", "parse_pdf"), {
                "error": "documentId is required"
            })
        key = f"{user_id}/{document_id}.pdf"
        obj = s3.get_object(Bucket=UPLOADS_BUCKET, Key=key)
        pdf_bytes = obj["Body"].read()
        parsed = llama_parse.parse_pdf_bytes(pdf_bytes, filename=f"{document_id}.pdf")
        return _ok_response(event.get("actionGroup", "DocParseTools"), event.get("function", "parse_pdf"), parsed)
    except Exception as exc:
        return _ok_response(event.get("actionGroup", "DocParseTools"), event.get("function", "parse_pdf"), {
            "error": str(exc)
        })
