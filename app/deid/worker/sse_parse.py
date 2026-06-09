"""Parse Ollama SSE chunks from Mac Worker stream frames."""
from __future__ import annotations

import json


def parse_ollama_sse_chunk(raw: str) -> str | None:
    """Extract delta.content from a Worker stream chunk (Ollama SSE text)."""
    if not raw:
        return None
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        choices = data.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if content:
            return str(content)
    return None
