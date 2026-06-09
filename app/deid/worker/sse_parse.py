"""Parse Ollama SSE chunks from Mac Worker stream frames."""
from __future__ import annotations

import json


def _iter_sse_payloads(raw: str):
    if not raw:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            yield json.loads(payload)
        except json.JSONDecodeError:
            continue


def parse_ollama_sse_chunk(raw: str) -> str | None:
    """Extract delta.content from a Worker stream chunk (Ollama SSE text)."""
    parts = parse_ollama_sse_tokens(raw)
    if not parts:
        return None
    return "".join(parts)


def parse_ollama_sse_tokens(raw: str) -> list[str]:
    """All delta.content pieces in one SSE chunk (may contain multiple data: lines)."""
    tokens: list[str] = []
    for data in _iter_sse_payloads(raw):
        choices = data.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                tokens.append(str(content))
                continue
        msg = data.get("message") or {}
        content = msg.get("content")
        if content:
            tokens.append(str(content))
    return tokens


def parse_ollama_sse_usage(raw: str) -> tuple[int, int]:
    """Return (prompt_tokens, completion_tokens) from Ollama stream frame if present."""
    prompt = 0
    completion = 0
    for data in _iter_sse_payloads(raw):
        if data.get("prompt_eval_count") is not None:
            prompt = int(data["prompt_eval_count"])
        if data.get("eval_count") is not None:
            completion = int(data["eval_count"])
    return prompt, completion
