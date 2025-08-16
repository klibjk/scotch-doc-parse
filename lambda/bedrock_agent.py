import json
import os
from typing import Any, Dict


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # Placeholder that returns a deterministic fake result for now
    prompt = event.get("prompt") if isinstance(event, dict) else None
    result = {
        "text": f"Echo: {prompt}" if prompt else "No prompt provided",
        "sources": [],
        "report": {"format": "markdown", "content": "# Report\n\nTBD"},
    }
    return {
        "agentResult": json.dumps(result),
        "completedAt": event.get("createdAt", ""),
        "sessionId": event.get("sessionId", ""),
    }
