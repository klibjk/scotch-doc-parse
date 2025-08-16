import json
import os
import time
from typing import Any, Dict

import boto3


dynamodb = boto3.resource("dynamodb")
tasks_table = dynamodb.Table(os.environ["AGENT_TASKS_TABLE"])


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    body = json.loads(event.get("body" or "{}"))
    prompt = body.get("prompt") or ""
    user_id = body.get("userId") or "anon"
    session_id = body.get("sessionId") or f"sess_{int(time.time()*1000)}"

    if not prompt:
        return {"statusCode": 400, "body": json.dumps({"message": "prompt is required"})}

    task_id = f"task_{int(time.time()*1000)}"
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    tasks_table.put_item(
        Item={
            "taskId": task_id,
            "status": "RUNNING",
            "prompt": prompt,
            "createdAt": created_at,
            "userId": user_id,
        }
    )

    # In v1, a Step Functions execution would be started here

    return {"statusCode": 200, "body": json.dumps({"taskId": task_id, "sessionId": session_id})}
