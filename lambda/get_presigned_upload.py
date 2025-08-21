import json
import os
import time
from typing import Any, Dict

import boto3


s3 = boto3.client("s3")
UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    body = json.loads(event.get("body" or "{}"))
    filename = body.get("filename") or "upload.pdf"
    content_type = body.get("contentType") or "application/pdf"
    user_id = body.get("userId") or "anon"

    document_id = f"doc_{int(time.time()*1000)}"
    # Determine extension from content type or filename fallback
    ext = "pdf"
    ct = (content_type or "").lower()
    if ct in ("application/pdf",):
        ext = "pdf"
    elif ct in ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",):
        ext = "xlsx"
    else:
        # Fallback to filename suffix
        lower = filename.lower()
        if lower.endswith(".xlsx"):
            ext = "xlsx"
        else:
            ext = "pdf"

    key = f"{user_id}/{document_id}.{ext}"

    # Include original filename as object metadata via presigned headers
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": UPLOADS_BUCKET,
            "Key": key,
            "ContentType": content_type,
            "Metadata": {"original-filename": filename},
        },
        ExpiresIn=900,
    )

    return {
        "statusCode": 200,
        "headers": {"Access-Control-Allow-Origin": "*"},
        "body": json.dumps(
            {
                "uploadUrl": url,
                "headers": {"x-amz-meta-original-filename": filename},
                "documentId": document_id,
                "extension": ext,
                "expiresIn": 900,
            }
        ),
    }
