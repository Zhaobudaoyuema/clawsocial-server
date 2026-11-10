from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import WebSocketDisconnect

from app.api import remote_command_v11
from app.remote_command import RemoteCommandError, RemoteCommandRelay
from app.remote_command_security import RemoteCommandInvite, token_hash


@pytest.fixture
def operator(monkeypatch):
    monkeypatch.setenv("REMOTE_COMMAND_OPERATOR_TOKEN", "test-operator")
    return {"Authorization": "Bearer test-operator"}


def register(client, operator, minutes=30):
    invite = client.post(
        "/api/remote-command/invites", headers=operator,
        json={"session_minutes": minutes},
    )
    assert invite.status_code == 200
    response = client.post(
        "/api/remote-command/targets/register",
        json={"invite_token": invite.json()["invite_token"]},
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("minutes", [10, 30, 180])
def test_register_consumes_persistent_invite(client, operator, db, minutes):
    invite = client.post(
        "/api/remote-command/invites", headers=operator,
        json={"session_minutes": minutes},
    ).json()
    payload = {"invite_token": invite["invite_token"]}
    response = client.post("/api/remote-command/targets/register", json=payload)
    assert response.status_code == 200
    target = response.json()
    assert target["expires_in_minutes"] == minutes
    assert target["connection_token"]
    assert target["websocket_path"] == f"/ws/remote-command/target?id={target['id']}"
    stored = db.get(RemoteCommandInvite, token_hash(invite["invite_token"]))
    assert stored.consumed_at is not None
    assert stored.token_hash != invite["invite_token"]
    assert client.post("/api/remote-command/targets/register", json=payload).status_code == 403


def test_expired_invite_cannot_register(client, operator, db):
    invite = client.post("/api/remote-command/invites", headers=operator, json={}).json()
    stored = db.get(RemoteCommandInvite, token_hash(invite["invite_token"]))
    stored.expires_at = 0
    db.commit()
    response = client.post(
        "/api/remote-command/targets/register", json={"invite_token": invite["invite_token"]},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/api/remote-command/invites", {}),
    ("GET", "/api/remote-command/targets", None),
    ("GET", "/api/remote-command/targets/unknown", None),
    ("POST", "/api/remote-command/execute", {"target_id": "unknown", "command": "echo test"}),
])
def test_operator_required_for_management(client, operator, method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401
    assert client.request(
        method, path, json=payload, headers={"Authorization": "Bearer incorrect"},
    ).status_code == 401


def test_operator_missing_fails_closed(client, monkeypatch, tmp_path):
    monkeypatch.delenv("REMOTE_COMMAND_OPERATOR_TOKEN", raising=False)
    monkeypatch.setenv("REMOTE_COMMAND_OPERATOR_TOKEN_FILE", str(tmp_path / "absent"))
    response = client.get("/api/remote-command/targets")
    assert response.status_code == 503
    assert response.json() == {"detail": "remote_command_operator_not_configured"}


def test_operator_can_be_read_from_file(client, monkeypatch, tmp_path):
    monkeypatch.delenv("REMOTE_COMMAND_OPERATOR_TOKEN", raising=False)
    path = tmp_path / "operator.token"
    path.write_text("test-file-token\n")
    monkeypatch.setenv("REMOTE_COMMAND_OPERATOR_TOKEN_FILE", str(path))
    assert client.get(
        "/api/remote-command/targets", headers={"Authorization": "Bearer test-file-token"},
    ).status_code == 200
    # A subsequent request resolves the current canonical file, not a cached token.
    path.write_text("replacement-token")
    assert client.get(
        "/api/remote-command/targets", headers={"Authorization": "Bearer test-file-token"},
    ).status_code == 401


def test_websocket_requires_its_own_connection_token(client, operator):
    target = register(client, operator)
    other = register(client, operator)
    for headers in ({}, operator, {"Authorization": f"Bearer {other['connection_token']}"}):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(target["websocket_path"], headers=headers):
                pass
        assert exc.value.code == 1008


def test_v12_execute_round_trip_and_duplicate_connection(client, operator):
    target = register(client, operator)
    headers = {"Authorization": f"Bearer {target['connection_token']}"}
    with client.websocket_connect(target["websocket_path"], headers=headers) as ws:
        assert ws.receive_json()["id"] == target["id"]
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(target["websocket_path"], headers=headers):
                pass
        result = {}

        def execute():
            result["response"] = client.post(
                "/api/remote-command/execute", headers=operator,
                json={"target_id": target["id"], "command": "echo hello", "timeout": 2},
            )

        thread = threading.Thread(target=execute)
        thread.start()
        message = ws.receive_json()
        assert message["command"] == "echo hello"
        ws.send_json({"type": "result", "request_id": message["request_id"],
                      "exit_code": 0, "stdout": "hello", "stderr": ""})
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert result["response"].status_code == 200
        assert result["response"].json()["stdout"] == "hello"


def test_v11_and_v12_grants_are_isolated(client, operator):
    modern = register(client, operator)
    legacy = client.post(
        "/legacy-v11/api/remote-command/targets/register",
        json={"target_id": "legacy-target"},
    )
    assert legacy.status_code == 200
    old_targets = client.get("/legacy-v11/api/remote-command/targets").json()["targets"]
    new_targets = client.get("/api/remote-command/targets", headers=operator).json()["targets"]
    assert [t["id"] for t in old_targets] == ["legacy-target"]
    assert [t["id"] for t in new_targets] == [modern["id"]]
    assert remote_command_v11.app.state.remote_command_relay is not client.app.state.remote_command_relay


def test_oversized_message_closes_websocket(client, operator):
    target = register(client, operator)
    with client.websocket_connect(
        target["websocket_path"], headers={"Authorization": f"Bearer {target['connection_token']}"},
    ) as ws:
        ws.receive_json()
        ws.send_text("x" * 262145)
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1009


def test_expired_connection_is_closed(client, operator):
    target = register(client, operator)
    client.app.state.remote_command_relay._grants[target["id"]].expires_at = (
        datetime.now(timezone.utc) + timedelta(milliseconds=100)
    )
    with client.websocket_connect(
        target["websocket_path"], headers={"Authorization": f"Bearer {target['connection_token']}"},
    ) as ws:
        ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1000


def test_result_and_disconnect_only_affect_own_target():
    class Socket:
        def __init__(self):
            self.sent = asyncio.Queue()

        async def send_json(self, payload):
            await self.sent.put(payload)

    async def scenario():
        relay = RemoteCommandRelay()
        first, second = Socket(), Socket()
        for name, ws in (("first", first), ("second", second)):
            await relay.register_target_id(name)
            await relay.attach(ws, name)
        task = asyncio.create_task(relay.execute(
            target_id="first", command="echo test", shell="sh", timeout=1,
        ))
        message = await first.sent.get()
        with pytest.raises(RemoteCommandError) as exc:
            await relay.execute(target_id="first", command="echo second", shell="sh", timeout=1)
        assert exc.value.status_code == 429
        await relay.handle_message({"type": "result", "target_id": "second",
                                    "request_id": message["request_id"], "stdout": "forged"})
        await relay.detach(second)
        assert not task.done()
        await relay.handle_message({"type": "result", "target_id": "first",
                                    "request_id": message["request_id"], "stdout": "correct"})
        result = await task
        assert result["stdout"] == "correct"

    asyncio.run(scenario())
