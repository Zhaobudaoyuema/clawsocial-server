"""Tests for deid local chat API."""
import json

import pytest


def test_create_chat_session_none(client):
    r = client.post("/api/deid/chat/sessions", data={"mode": "none"})
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"]
    assert data["has_doc"] is False


def test_chat_message_worker_offline_sse(client):
    r = client.post("/api/deid/chat/sessions", data={"mode": "none"})
    session_id = r.json()["session_id"]
    r = client.post(
        f"/api/deid/chat/sessions/{session_id}/messages",
        json={"content": "你好"},
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    body = r.text
    assert "worker_offline" in body or "error" in body


@pytest.mark.asyncio
async def test_stream_sse_parse():
    from app.deid.worker.sse_parse import parse_ollama_sse_chunk

    chunk = 'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'
    assert parse_ollama_sse_chunk(chunk) == "你"
