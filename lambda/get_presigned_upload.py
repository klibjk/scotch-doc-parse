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
    key = f"{user_id}/{document_id}.pdf"

    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": UPLOADS_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=900,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({"uploadUrl": url, "documentId": document_id, "expiresIn": 900}),
    }
