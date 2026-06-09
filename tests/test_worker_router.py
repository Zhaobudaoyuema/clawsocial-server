"""Unit tests for Mac Worker WebSocket router."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.deid.worker.errors import WorkerBusy, WorkerOffline, WorkerRequestError
from app.deid.worker.router import WorkerRouter


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.client_state = WebSocketState.CONNECTED

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


@pytest.mark.asyncio
async def test_register_and_status():
    router = WorkerRouter()
    ws = FakeWebSocket()
    await router.attach(ws)

    await router.handle_message(
        json.dumps(
            {
                "type": "register",
                "hostname": "macbook",
                "model": "qwen3.5:4b-mlx",
                "version": "0.2.0",
            }
        )
    )
    await router.handle_message(json.dumps({"type": "status", "state": "ready"}))

    status = router.status_dict()
    assert status["online"] is True
    assert status["model"] == "qwen3.5:4b-mlx"
    assert status["state"] == "ready"


@pytest.mark.asyncio
async def test_chat_completions_success():
    router = WorkerRouter()
    ws = FakeWebSocket()
    await router.attach(ws)
    await router.handle_message(json.dumps({"type": "status", "state": "ready"}))

    async def respond():
        await asyncio.sleep(0.01)
        payload = ws.sent[-1]
        await router.handle_message(
            json.dumps(
                {
                    "id": payload["id"],
                    "status": 200,
                    "body": {
                        "choices": [{"message": {"content": '{"entities":[]}'}}],
                    },
                }
            )
        )

    task = asyncio.create_task(respond())
    body = await router.chat_completions({"model": "test", "messages": []}, timeout=5)
    await task
    assert "choices" in body


@pytest.mark.asyncio
async def test_chat_completions_offline():
    router = WorkerRouter()
    with pytest.raises(WorkerOffline):
        await router.chat_completions({"model": "test", "messages": []})


@pytest.mark.asyncio
async def test_chat_completions_busy_state():
    router = WorkerRouter()
    ws = FakeWebSocket()
    await router.attach(ws)
    await router.handle_message(json.dumps({"type": "status", "state": "busy"}))
    with pytest.raises(WorkerBusy):
        await router.chat_completions({"model": "test", "messages": []})


@pytest.mark.asyncio
async def test_chat_completions_429_retry():
    router = WorkerRouter()
    ws = FakeWebSocket()
    await router.attach(ws)
    await router.handle_message(json.dumps({"type": "status", "state": "ready"}))
    attempts = {"n": 0}

    async def respond():
        seen = 0
        while seen < 3:
            await asyncio.sleep(0.02)
            if len(ws.sent) <= seen:
                continue
            payload = ws.sent[seen]
            seen += 1
            attempts["n"] += 1
            if attempts["n"] < 2:
                await router.handle_message(
                    json.dumps({"id": payload["id"], "status": 429, "body": {"error": "busy"}})
                )
            else:
                await router.handle_message(
                    json.dumps(
                        {
                            "id": payload["id"],
                            "status": 200,
                            "body": {"choices": []},
                        }
                    )
                )
                return

    task = asyncio.create_task(respond())
    body = await router.chat_completions(
        {"model": "test", "messages": []},
        timeout=5,
        max_retries=3,
    )
    await task
    assert body == {"choices": []}
    assert attempts["n"] == 2


@pytest.mark.asyncio
async def test_chat_completions_error_status():
    router = WorkerRouter()
    ws = FakeWebSocket()
    await router.attach(ws)
    await router.handle_message(json.dumps({"type": "status", "state": "ready"}))

    async def respond():
        await asyncio.sleep(0.01)
        payload = ws.sent[-1]
        await router.handle_message(
            json.dumps({"id": payload["id"], "status": 502, "body": {"error": "ollama down"}})
        )

    task = asyncio.create_task(respond())
    with pytest.raises(WorkerRequestError) as exc:
        await router.chat_completions({"model": "test", "messages": []}, timeout=5)
    await task
    assert exc.value.status == 502


@pytest.mark.asyncio
async def test_chat_completions_stream():
    router = WorkerRouter()
    ws = FakeWebSocket()
    await router.attach(ws)
    await router.handle_message(json.dumps({"type": "status", "state": "ready"}))

    async def respond():
        await asyncio.sleep(0.02)
        payload = ws.sent[-1]
        req_id = payload["id"]
        await router.handle_message(
            json.dumps(
                {
                    "id": req_id,
                    "status": 200,
                    "stream": True,
                    "done": False,
                    "chunk": 'data: {"choices":[{"delta":{"content":"A"}}]}\n\n',
                }
            )
        )
        await router.handle_message(
            json.dumps({"id": req_id, "status": 200, "stream": True, "done": True})
        )

    task = asyncio.create_task(respond())
    tokens = []
    async for t in router.chat_completions_stream({"model": "test", "messages": []}, timeout=5):
        tokens.append(t)
    await task
    assert tokens == ["A"]
