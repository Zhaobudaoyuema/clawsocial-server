"""Tests for DEID dev worker relay (local → remote Mac Worker)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.deid.worker.relay_auth import TOKEN_ENV, IPS_ENV
from app.deid.worker.relay_client import RemoteWorkerRelay, URL_ENV
from app.deid.worker.router import WorkerRouter
from app.main import app


@pytest.fixture
def relay_token(monkeypatch):
    monkeypatch.setenv("DEID_DEV_RELAY_TOKEN", "test-relay-secret")
    monkeypatch.delenv(IPS_ENV, raising=False)
    return "test-relay-secret"


@pytest.fixture
def client_with_relay(relay_token):
    from app.api import deid_dev

    deid_dev.include_dev_relay_routes(app)
    with TestClient(app) as tc:
        yield tc


@pytest.mark.asyncio
async def test_relay_status_requires_token(client_with_relay):
    resp = client_with_relay.get("/api/deid/dev/worker/status")
    assert resp.status_code == 401

    resp = client_with_relay.get(
        "/api/deid/dev/worker/status",
        headers={"Authorization": "Bearer test-relay-secret"},
    )
    assert resp.status_code == 200
    assert resp.json()["online"] is False


@pytest.mark.asyncio
async def test_relay_chat_worker_offline(client_with_relay):
    resp = client_with_relay.post(
        "/api/deid/dev/worker/chat-completions",
        headers={"Authorization": "Bearer test-relay-secret"},
        json={"body": {"model": "m", "messages": []}, "stream": False},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_relay_chat_forwards(client_with_relay):
    router: WorkerRouter = client_with_relay.app.state.worker_router
    ws = _FakeWs()
    await router.attach(ws)
    await router.handle_message(
        json.dumps(
            {
                "type": "register",
                "hostname": "mac",
                "model": "qwen-test",
                "version": "0.1",
            }
        )
    )
    await router.handle_message(json.dumps({"type": "status", "state": "ready"}))

    async def fake_chat(body, **kwargs):
        return {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        }

    router.chat_completions = fake_chat  # type: ignore[method-assign]

    resp = client_with_relay.post(
        "/api/deid/dev/worker/chat-completions",
        headers={"X-Deid-Relay-Token": "test-relay-secret"},
        json={
            "body": {
                "model": "qwen-test",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            }
        },
    )
    assert resp.status_code == 200
    assert resp.json()["body"]["choices"][0]["message"]["content"] == "ok"


@pytest.mark.asyncio
async def test_relay_ip_allowlist(client_with_relay, monkeypatch):
    monkeypatch.setenv(IPS_ENV, "203.0.113.50")
    resp = client_with_relay.get(
        "/api/deid/dev/worker/status",
        headers={"Authorization": "Bearer test-relay-secret"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_remote_worker_relay_client(monkeypatch):
    monkeypatch.setenv(URL_ENV, "https://example.com")
    monkeypatch.setenv("DEID_WORKER_RELAY_TOKEN", "tok")

    relay = RemoteWorkerRelay()
    assert relay.enabled is True
    assert relay.session is None

    async def fake_refresh():
        relay._status = {
            "online": True,
            "state": "ready",
            "model": "qwen-test",
            "hostname": "mac",
            "version": "0.1",
        }
        relay._status_at = 0

    relay.refresh_status = fake_refresh  # type: ignore[method-assign]
    await relay.refresh_status()
    assert relay.session is not None
    assert relay.session.model == "qwen-test"


def test_machine_guid_token_allowed():
    from app.deid.worker.dev_machine_token import (
        ALLOWED_DEV_MACHINE_GUIDS,
        get_local_dev_relay_token,
        is_allowed_relay_token,
        token_from_machine_guid,
    )

    guid = next(iter(ALLOWED_DEV_MACHINE_GUIDS))
    token = token_from_machine_guid(guid)
    assert is_allowed_relay_token(token)
    assert get_local_dev_relay_token() == token


class _FakeWs:
    client_state = 1

    async def send_json(self, data):
        pass
