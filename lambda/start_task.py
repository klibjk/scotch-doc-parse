import json
import os
import time
from typing import Any, Dict

import boto3
from botocore.config import Config


sfn = boto3.client("stepfunctions", config=Config(retries={"max_attempts": 3}))
dynamodb = boto3.resource("dynamodb")
tasks_table = dynamodb.Table(os.environ["AGENT_TASKS_TABLE"])
SFN_ARN = os.environ.get("SFN_ARN", "")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    body = json.loads(event.get("body" or "{}"))
    prompt = body.get("prompt") or ""
    document_ids = body.get("documentIds") or []
    user_id = body.get("userId") or "anon"
    session_id = body.get("sessionId") or f"sess_{int(time.time()*1000)}"

    if not prompt:
        return {"statusCode": 400, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"message": "prompt is required"})}

    task_id = f"task_{int(time.time()*1000)}"
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    tasks_table.put_item(
        Item={
            "taskId": task_id,
            "status": "RUNNING",
            "prompt": prompt,
            "createdAt": created_at,
            "userId": user_id,
            "docRefs": document_ids,
        }
    )

    # Start Step Functions execution (fire-and-forget)
    if SFN_ARN:
        input_obj = {
            "taskId": task_id,
            "prompt": prompt,
            "createdAt": created_at,
            "userId": user_id,
            "sessionId": session_id,
            "documentIds": document_ids,
        }
        try:
            sfn.start_execution(stateMachineArn=SFN_ARN, input=json.dumps(input_obj))
        except Exception as exc:
            # Mark task as failed if we cannot start the execution
            tasks_table.update_item(
                Key={"taskId": task_id},
                UpdateExpression="SET #status=:s, #error=:e",
                ExpressionAttributeNames={"#status": "status", "#error": "error"},
                ExpressionAttributeValues={":s": "FAILED", ":e": str(exc)},
            )
            return {"statusCode": 500, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"message": "Failed to start task"})}
    return {"statusCode": 200, "headers": {"Access-Control-Allow-Origin": "*"}, "body": json.dumps({"taskId": task_id, "sessionId": session_id})}
