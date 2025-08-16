import json
import os
import time
from typing import Any, Dict


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # Placeholder that returns a deterministic fake result for now
    prompt = event.get("prompt") if isinstance(event, dict) else None
    result = {
        "text": f"Echo: {prompt}" if prompt else "No prompt provided",
        "sources": [],
        "report": {"format": "markdown", "content": "# Report\n\nTBD"},
    }
    completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "agentResult": json.dumps(result),
        "completedAt": completed_at,
        "sessionId": event.get("sessionId", ""),
    }
