import json
import os
import time
import random
from typing import Any, Dict
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

AGENT_ID = os.environ["BEDROCK_AGENT_ID"]
AGENT_ALIAS_ID = os.environ["BEDROCK_AGENT_ALIAS_ID"]

brt = boto3.client("bedrock-agent-runtime", config=Config(retries={"max_attempts": 1}))


def _is_throttling_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    if "throttling" in msg or "rate" in msg:
        return True
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        return code.lower() in {
            "throttling",
            "throttlingexception",
            "throttled",
            "throttlingerror",
            "toomanyrequestsexception",
            "throttlingerrorexception",
        }
    return False


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    body = json.loads(event.get("body") or "{}")
    prompt = body.get("prompt") or ""
    session_id = body.get("sessionId") or f"sess-{int(time.time()*1000)}"

    if not prompt:
        return {
            "statusCode": 400,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"message": "prompt is required"}),
        }

    max_retries = 3
    base_delay = 1.0  # seconds
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = brt.invoke_agent(
                agentId=AGENT_ID,
                agentAliasId=AGENT_ALIAS_ID,
                sessionId=session_id,
                inputText=prompt,
            )
            chunks = []
            try:
                for ev in resp.get("completion", []):
                    chunk = ev.get("chunk") or {}
                    txt = chunk.get("bytes")
                    if isinstance(txt, (bytes, bytearray)):
                        try:
                            chunks.append(txt.decode("utf-8"))
                        except Exception:
                            pass
            except Exception as stream_exc:
                # If throttled during streaming, do not re-invoke to avoid bursty retries.
                # Return any partial content if present; otherwise surface a 429-like error.
                if _is_throttling_error(stream_exc):
                    if chunks:
                        text = "".join(chunks)
                        return {
                            "statusCode": 200,
                            "headers": {"Access-Control-Allow-Origin": "*"},
                            "body": json.dumps({"text": text, "sessionId": session_id}),
                        }
                    last_exc = stream_exc
                    break
                raise
            text = "".join(chunks)
            return {
                "statusCode": 200,
                "headers": {"Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"text": text, "sessionId": session_id}),
            }
        except Exception as exc:
            if _is_throttling_error(exc) and attempt < max_retries - 1:
                delay = base_delay * (2**attempt) * (0.5 + random.random())
                time.sleep(delay)
                last_exc = exc
                continue
            last_exc = exc
            break

    return {
        "statusCode": 429,
        "headers": {"Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"message": str(last_exc) if last_exc else "Throttled"}),
    }
