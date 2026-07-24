from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone


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
    assert status_data["registered"] is True
    assert status_data["expired"] is False
    assert status_data["expires_at"] == data["expires_at"]


def test_register_target_accepts_half_hour(client):
    resp = _register(client, expires_in_minutes=30)

    assert resp.status_code == 200
    assert resp.json()["expires_in_minutes"] == 30


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
