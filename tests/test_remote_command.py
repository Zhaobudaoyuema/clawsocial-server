from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone

from app.main import _seconds_until_next_remote_command_reset
from app.remote_command import RemoteCommandRelay


def _register(client, target_id="pc-home", expires_in_minutes=10):
    return client.post(
        "/api/remote-command/targets/register",
        json={"target_id": target_id, "expires_in_minutes": expires_in_minutes},
    )


def test_register_target_returns_id(client):
    resp = _register(client)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "pc-home"
    assert data["expires_in_minutes"] == 10
    assert data["expires_at"]
    assert data["websocket_path"] == "/ws/remote-command/target?id=pc-home"

    status = client.get("/api/remote-command/targets/pc-home")
    status_data = status.json()
    assert status_data["id"] == "pc-home"
    assert status_data["online"] is False
    assert status_data["state"] == "offline_authorized"
    assert status_data["registered"] is True
    assert status_data["expired"] is False
    assert status_data["expires_at"] == data["expires_at"]


def test_register_target_accepts_half_hour(client):
    resp = _register(client, expires_in_minutes=30)

    assert resp.status_code == 200
    assert resp.json()["expires_in_minutes"] == 30


def test_register_target_accepts_three_hours(client):
    resp = _register(client, expires_in_minutes=180)

    assert resp.status_code == 200
    assert resp.json()["expires_in_minutes"] == 180


def test_rejects_invalid_target_id(client):
    resp = _register(client, target_id="../bad")

    assert resp.status_code == 400


def test_rejects_invalid_expiration(client):
    resp = client.post(
        "/api/remote-command/targets/register",
        json={"target_id": "pc-home", "expires_in_minutes": 60},
    )

    assert resp.status_code == 422


def test_execute_round_trip(client):
    registered_target = _register(client).json()
    with client.websocket_connect("/ws/remote-command/target?id=pc-home") as ws:
        registered = ws.receive_json()
        assert registered == {
            "type": "registered",
            "id": "pc-home",
            "expires_at": registered_target["expires_at"],
        }
        ws.send_json(
            {
                "type": "hello",
                "hostname": "workstation",
                "platform": "Windows",
                "shell": "cmd",
            }
        )

        result_box = {}

        def post_execute():
            result_box["resp"] = client.post(
                "/api/remote-command/execute",
                json={
                    "target_id": "pc-home",
                    "command": "echo hello",
                    "shell": "cmd",
                    "timeout": 5,
                },
            )

        thread = threading.Thread(target=post_execute)
        thread.start()

        request = ws.receive_json()
        assert request["type"] == "exec"
        assert request["command"] == "echo hello"
        assert request["shell"] == "cmd"

        ws.send_json(
            {
                "type": "result",
                "request_id": request["request_id"],
                "exit_code": 0,
                "stdout": "hello\r\n",
                "stderr": "",
                "duration_ms": 12,
            }
        )
        thread.join(timeout=5)

    resp = result_box["resp"]
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_id"] == "pc-home"
    assert data["exit_code"] == 0
    assert data["stdout"] == "hello\r\n"


def test_execute_defaults_to_cmd(client):
    _register(client)
    with client.websocket_connect("/ws/remote-command/target?id=pc-home") as ws:
        registered = ws.receive_json()
        assert registered["type"] == "registered"
        assert registered["id"] == "pc-home"

        result_box = {}

        def post_execute():
            result_box["resp"] = client.post(
                "/api/remote-command/execute",
                json={
                    "target_id": "pc-home",
                    "command": "echo hello",
                    "timeout": 5,
                },
            )

        thread = threading.Thread(target=post_execute)
        thread.start()

        request = ws.receive_json()
        assert request["shell"] == "cmd"

        ws.send_json(
            {
                "type": "result",
                "request_id": request["request_id"],
                "exit_code": 0,
                "stdout": "hello\r\n",
                "stderr": "",
            }
        )
        thread.join(timeout=5)

    assert result_box["resp"].status_code == 200


def test_status_tracks_offline_after_window_closed(client):
    registered_target = _register(client).json()
    with client.websocket_connect("/ws/remote-command/target?id=pc-home") as ws:
        assert ws.receive_json()["type"] == "registered"
        ws.send_json(
            {
                "type": "hello",
                "hostname": "workstation",
                "platform": "Windows",
                "shell": "cmd",
            }
        )
        online = client.get("/api/remote-command/targets/pc-home").json()
        assert online["state"] == "online"
        assert online["online"] is True
        assert online["hostname"] == "workstation"

    offline = client.get("/api/remote-command/targets/pc-home").json()
    assert offline["state"] == "offline_authorized"
    assert offline["online"] is False
    assert offline["registered"] is True
    assert offline["expired"] is False
    assert offline["expires_at"] == registered_target["expires_at"]
    assert offline["hostname"] == "workstation"
    assert offline["disconnected_at"]

    resp = client.post(
        "/api/remote-command/execute",
        json={"target_id": "pc-home", "command": "echo hello", "timeout": 5},
    )

    assert resp.status_code == 409
    assert resp.json() == {"detail": "target_offline"}


def test_execute_rejects_expired_target(client):
    _register(client)
    relay = client.app.state.remote_command_relay
    relay._grants["pc-home"].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    resp = client.post(
        "/api/remote-command/execute",
        json={"target_id": "pc-home", "command": "echo hello", "timeout": 5},
    )

    assert resp.status_code == 410
    assert resp.json() == {"detail": "target_expired"}


def test_execute_requires_operator_token_when_configured(client, monkeypatch):
    monkeypatch.setenv("REMOTE_COMMAND_OPERATOR_TOKEN", "secret-token")

    resp = client.post(
        "/api/remote-command/execute",
        json={"target_id": "pc-home", "command": "echo hello", "timeout": 5},
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "remote_command_operator_token_required"}


def test_execute_does_not_require_operator_token_when_unconfigured(client, monkeypatch):
    monkeypatch.delenv("REMOTE_COMMAND_OPERATOR_TOKEN", raising=False)
    _register(client)
    with client.websocket_connect("/ws/remote-command/target?id=pc-home") as ws:
        assert ws.receive_json()["type"] == "registered"

        result_box = {}

        def post_execute():
            result_box["resp"] = client.post(
                "/api/remote-command/execute",
                json={"target_id": "pc-home", "command": "echo hello", "timeout": 5},
            )

        thread = threading.Thread(target=post_execute)
        thread.start()
        request = ws.receive_json()
        ws.send_json(
            {
                "type": "result",
                "request_id": request["request_id"],
                "exit_code": 0,
                "stdout": "hello\r\n",
                "stderr": "",
            }
        )
        thread.join(timeout=5)

    assert result_box["resp"].status_code == 200


def test_execute_accepts_operator_token_when_configured(client, monkeypatch):
    monkeypatch.setenv("REMOTE_COMMAND_OPERATOR_TOKEN", "secret-token")
    _register(client)
    with client.websocket_connect("/ws/remote-command/target?id=pc-home") as ws:
        assert ws.receive_json()["type"] == "registered"

        result_box = {}

        def post_execute():
            result_box["resp"] = client.post(
                "/api/remote-command/execute",
                headers={"Authorization": "Bearer secret-token"},
                json={"target_id": "pc-home", "command": "echo hello", "timeout": 5},
            )

        thread = threading.Thread(target=post_execute)
        thread.start()
        request = ws.receive_json()
        ws.send_json(
            {
                "type": "result",
                "request_id": request["request_id"],
                "exit_code": 0,
                "stdout": "hello\r\n",
                "stderr": "",
            }
        )
        thread.join(timeout=5)

    assert result_box["resp"].status_code == 200


def test_clear_all_removes_grants():
    async def scenario():
        relay = RemoteCommandRelay()
        await relay.register_target_id("pc-home", expires_in_minutes=180)

        stats = await relay.clear_all(reason="test_reset")

        assert stats == {"grants": 1, "sessions": 0, "pending": 0}
        assert relay.target_status("pc-home") == {
            "id": "pc-home",
            "online": False,
            "state": "unregistered",
            "registered": False,
            "expired": False,
        }

    asyncio.run(scenario())


def test_remote_command_reset_runs_at_next_beijing_4am():
    now = datetime(2026, 7, 25, 3, 30, tzinfo=timezone(timedelta(hours=8)))
    assert _seconds_until_next_remote_command_reset(now) == 30 * 60

    now = datetime(2026, 7, 25, 4, 0, tzinfo=timezone(timedelta(hours=8)))
    assert _seconds_until_next_remote_command_reset(now) == 24 * 60 * 60
