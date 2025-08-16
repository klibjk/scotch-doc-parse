import json
import os
from typing import Any, Dict

import boto3


dynamodb = boto3.resource("dynamodb")
tasks_table = dynamodb.Table(os.environ["AGENT_TASKS_TABLE"])


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    params = event.get("queryStringParameters") or {}
    task_id = params.get("taskId") if isinstance(params, dict) else None

    if not task_id:
        return {"statusCode": 400, "body": json.dumps({"message": "taskId is required"})}

    item = tasks_table.get_item(Key={"taskId": task_id}).get("Item")
    if not item:
        return {"statusCode": 404, "body": json.dumps({"message": "Not found"})}

    return {"statusCode": 200, "body": json.dumps({"taskId": task_id, "status": item.get("status"), "result": item.get("result"), "error": item.get("error")})}
