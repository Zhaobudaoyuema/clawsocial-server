"""Exercise actual agent serialization through both relay WebSocket routes."""
import asyncio
import json
import threading

import pytest

from app.remote_command import RemoteCommandRelay, RemoteCommandError
from scripts.remote_command_output import send_result


class AgentSocket:
    def __init__(self, ws):
        self.ws = ws
        self.frames = []

    async def send(self, text):
        self.frames.append(text)
        self.ws.send_text(text)


@pytest.mark.parametrize("version", ["v11", "v12"])
def test_large_output_and_next_command_keep_connection(client, monkeypatch, version):
    monkeypatch.setenv("REMOTE_COMMAND_OPERATOR_TOKEN", "test-operator")
    headers = {"Authorization": "Bearer test-operator"} if version == "v12" else {}
    prefix = "/legacy-v11" if version == "v11" else ""
    if version == "v11":
        target = client.post(prefix + "/api/remote-command/targets/register", json={}).json()
        ws_headers = {}
    else:
        invite = client.post("/api/remote-command/invites", headers=headers, json={}).json()
        target = client.post("/api/remote-command/targets/register",
                             json={"invite_token": invite["invite_token"]}).json()
        ws_headers = {"Authorization": "Bearer " + target["connection_token"]}
    with client.websocket_connect(prefix + target["websocket_path"], headers=ws_headers) as ws:
        assert ws.receive_json()["result_chunks"] == 1
        socket = AgentSocket(ws)
        # Multibyte Unicode, JSON quoting, control characters, both streams.
        for stdout, stderr in [(('日志😀"\\\n\x00' * 100000), ('错误\r\n' * 30000)), ("still connected", "")]:
            box = {}
            def execute():
                box["response"] = client.post(prefix + "/api/remote-command/execute", headers=headers,
                    json={"target_id": target["id"], "command": "synthetic probe", "timeout": 5})
            thread = threading.Thread(target=execute)
            thread.start()
            request = ws.receive_json()
            asyncio.run(send_result(socket, request["request_id"],
                                    {"stdout": stdout, "stderr": stderr, "exit_code": 7, "duration_ms": 12},
                                    chunks_supported=True))
            thread.join(timeout=8)
            assert not thread.is_alive()
            response = box["response"]
            assert response.status_code == 200
            assert response.json() == {"request_id": request["request_id"], "target_id": target["id"],
                                       "stdout": stdout, "stderr": stderr, "exit_code": 7, "duration_ms": 12}
            assert client.get(prefix + "/api/remote-command/targets/" + target["id"], headers=headers).json()["online"]
        assert all(len(frame.encode()) < 262144 for frame in socket.frames)
        assert any(json.loads(frame)["type"] == "result_chunk" for frame in socket.frames)


def test_legacy_agent_large_single_result_is_accepted(client):
    prefix = "/legacy-v11"
    target = client.post(prefix + "/api/remote-command/targets/register", json={}).json()
    with client.websocket_connect(prefix + target["websocket_path"]) as ws:
        ws.receive_json()
        box = {}
        def execute():
            box["response"] = client.post(prefix + "/api/remote-command/execute",
                json={"target_id": target["id"], "command": "synthetic", "timeout": 5})
        thread = threading.Thread(target=execute)
        thread.start()
        request = ws.receive_json()
        output = "旧版日志" * 100000
        ws.send_json({"type": "result", "request_id": request["request_id"],
                      "exit_code": 0, "stdout": output, "stderr": ""})
        thread.join(timeout=8)
        assert not thread.is_alive()
        assert box["response"].json()["stdout"] == output
        assert client.get(prefix + "/api/remote-command/targets/" + target["id"]).json()["online"]


@pytest.mark.parametrize("bad_message,code", [
    ({"type": "result_chunk", "sequence": 2, "stream": "stdout", "data": "lost"}, 502),
    ({"type": "result_chunk", "sequence": 1, "stream": "invalid", "data": "bad"}, 502),
    ({"type": "result", "chunk_count": 2}, 502),
    ({"type": "result", "chunk_count": 1, "stdout": "mixed"}, 502),
    ({"type": "result_chunk", "sequence": 1, "stream": "stdout", "data": "x" * 101}, 413),
])
def test_bad_transfer_fails_only_command_and_releases_buffers(monkeypatch, bad_message, code):
    monkeypatch.setattr("app.remote_command.MAX_RESULT_BYTES", 100)
    class Socket:
        def __init__(self):
            self.sent = asyncio.Queue()
        async def send_json(self, data):
            await self.sent.put(data)
    async def scenario():
        relay, ws = RemoteCommandRelay(), Socket()
        await relay.register_target_id("probe")
        await relay.attach(ws, "probe")
        task = asyncio.create_task(relay.execute(target_id="probe", command="synthetic", timeout=1))
        request = await ws.sent.get()
        common = {"target_id": "probe", "request_id": request["request_id"]}
        # A different target cannot poison this command's chunk sequence.
        await relay.handle_message({**common, "target_id": "foreign", **bad_message})
        assert not task.done()
        await relay.handle_message({**common, "type": "result_chunk", "sequence": 0,
                                    "stream": "stdout", "data": "first"})
        await relay.handle_message({**common, **bad_message})
        with pytest.raises(RemoteCommandError) as exc:
            await task
        assert exc.value.status_code == code
        assert not relay._pending
        assert relay.target_status("probe")["online"]
    asyncio.run(scenario())


def test_timeout_output_bytes_and_old_server_fallback():
    class Socket:
        def __init__(self):
            self.frames = []
        async def send(self, text):
            self.frames.append(json.loads(text))
    async def scenario():
        ws = Socket()
        await send_result(ws, "timeout", {"stdout": b'partial\xff', "stderr": "timed out", "exit_code": 124},
                          chunks_supported=True)
        assert ws.frames[0]["stdout"] == "partial�"
        assert ws.frames[0]["exit_code"] == 124
        await send_result(ws, "large", {"stdout": "x" * 300000, "exit_code": 0}, chunks_supported=False)
        assert ws.frames[-1]["exit_code"] == 125
        assert "already ran" in ws.frames[-1]["stderr"]
    asyncio.run(scenario())
