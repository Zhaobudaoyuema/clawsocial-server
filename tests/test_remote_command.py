from __future__ import annotations

import threading


def test_register_target_returns_id(client):
    resp = client.post("/api/remote-command/targets/register", json={"target_id": "pc-home"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "pc-home"
    assert data["websocket_path"] == "/ws/remote-command/target?id=pc-home"

    status = client.get("/api/remote-command/targets/pc-home")
    assert status.json() == {"id": "pc-home", "online": False, "registered": True}


def test_rejects_invalid_target_id(client):
    resp = client.post("/api/remote-command/targets/register", json={"target_id": "../bad"})

    assert resp.status_code == 400


def test_execute_round_trip(client):
    with client.websocket_connect("/ws/remote-command/target?id=pc-home") as ws:
        registered = ws.receive_json()
        assert registered == {"type": "registered", "id": "pc-home"}
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
    with client.websocket_connect("/ws/remote-command/target?id=pc-home") as ws:
        assert ws.receive_json() == {"type": "registered", "id": "pc-home"}

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
