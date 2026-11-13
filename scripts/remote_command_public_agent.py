"""Standalone unrestricted controlled-computer agent for ClawSocial commands.

Run this script on the controlled computer. It registers a short-lived target id
with the relay server, prints the authorization id, then keeps a WebSocket
connection open until the local authorization window expires. This is intended
to run in the foreground; closing the terminal window disconnects the target.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import secrets
import subprocess
import sys
import time
from functools import partial
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import websockets

if __package__:
    from .remote_command_output import send_result
else:
    from remote_command_output import send_result


DEFAULT_BASE_URL = "http://clawsocial.world"
DEFAULT_EXPIRES_IN_MINUTES = 180
ALLOWED_EXPIRES_IN_MINUTES = {10, 30, 180}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register this computer as a short-lived remote command target."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("REMOTE_COMMAND_BASE_URL", DEFAULT_BASE_URL),
        help=f"relay server URL, default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--id",
        default=os.environ.get("REMOTE_COMMAND_TARGET_ID"),
        help="authorization id to share with the operator; auto-generated when omitted",
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=int(os.environ.get("REMOTE_COMMAND_EXPIRES_IN_MINUTES", DEFAULT_EXPIRES_IN_MINUTES)),
        choices=sorted(ALLOWED_EXPIRES_IN_MINUTES),
        help="authorization window in minutes, default: 180",
    )
    return parser.parse_args()


def generate_target_id() -> str:
    host = platform.node() or "pc"
    safe_host = "".join(ch if ch.isalnum() else "-" for ch in host.lower()).strip("-")
    safe_host = safe_host[:24] or "pc"
    return f"{safe_host}-{secrets.token_urlsafe(5).replace('-', '').replace('_', '')}"


class TargetAgent:
    def __init__(self, *, base_url: str, target_id: str, expires_in_minutes: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.target_id = target_id
        self.expires_in_minutes = expires_in_minutes
        self.local_expires_at = time.monotonic() + expires_in_minutes * 60

    def remaining_seconds(self) -> float:
        return max(0.0, self.local_expires_at - time.monotonic())

    def ws_url(self) -> str:
        if self.base_url.startswith("https://"):
            root = "wss://" + self.base_url[len("https://"):]
        elif self.base_url.startswith("http://"):
            root = "ws://" + self.base_url[len("http://"):]
        else:
            root = self.base_url
        return f"{root}/ws/remote-command/target?id={quote(self.target_id)}"

    def register(self) -> dict:
        body = json.dumps(
            {
                "target_id": self.target_id,
                "expires_in_minutes": self.expires_in_minutes,
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/remote-command/targets/register",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"register failed: HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise SystemExit(f"register failed: {exc}") from exc

    def run_command(self, command: str, shell_name: str | None, timeout: float) -> dict:
        if self.remaining_seconds() <= 0:
            return self.error_result(125, "local authorization expired")

        shell_name = (shell_name or ("cmd" if os.name == "nt" else "sh")).lower()
        if shell_name == "cmd":
            args = ["cmd.exe", "/d", "/s", "/c", command]
        elif shell_name == "powershell":
            args = ["powershell.exe", "-NoProfile", "-Command", command]
        elif shell_name == "pwsh":
            args = ["pwsh", "-NoProfile", "-Command", command]
        elif shell_name == "sh":
            args = ["sh", "-lc", command]
        else:
            args = ["bash", "-lc", command]

        started = time.monotonic()
        fallback_note = ""
        try:
            try:
                completed = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                )
            except FileNotFoundError:
                if os.name == "nt" or shell_name not in {"cmd", "powershell", "pwsh"}:
                    raise
                fallback_note = (
                    f"requested shell '{shell_name}' is unavailable on this target; "
                    "retried this command with 'sh'"
                )
                completed = subprocess.run(
                    ["sh", "-lc", command],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                )
            stderr = completed.stderr
            if fallback_note:
                stderr = f"{fallback_note}\n{stderr}".rstrip() + "\n"
            return {
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": stderr,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "exit_code": 124,
                "stdout": exc.stdout or "",
                "stderr": "command timed out",
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        except OSError as exc:
            return {
                "exit_code": 127,
                "stdout": "",
                "stderr": f"unable to start command shell: {exc}",
                "duration_ms": int((time.monotonic() - started) * 1000),
            }

    @staticmethod
    def error_result(exit_code: int, message: str) -> dict:
        return {
            "exit_code": exit_code,
            "stdout": "",
            "stderr": message,
            "duration_ms": 0,
        }

    async def run(self) -> None:
        registration = self.register()
        print("=" * 64)
        print(f"授权 id: {registration['id']}")
        print(f"有效期: {self.expires_in_minutes} 分钟")
        print(f"服务端到期时间: {registration.get('expires_at')}")
        print("执行策略: unrestricted（授权期内不拦截命令）")
        print("把上面的授权 id 发给操作者。保持这个窗口打开。")
        print("这个脚本必须前台运行；关闭当前终端窗口后，被操作者会立刻离线。")
        print("=" * 64, flush=True)

        async with websockets.connect(
            self.ws_url(),
            ping_interval=20,
            ping_timeout=60,
            close_timeout=10,
        ) as websocket:
            registered_message = await websocket.recv()
            chunks_supported = json.loads(registered_message).get("result_chunks") == 1
            print(f"已连接服务端: {registered_message}", flush=True)
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "target_id": self.target_id,
                        "hostname": platform.node(),
                        "platform": platform.platform(),
                        "shell": "cmd" if os.name == "nt" else "sh",
                        "execution_policy": "unrestricted",
                    }
                )
            )
            while self.remaining_seconds() > 0:
                try:
                    raw = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=self.remaining_seconds(),
                    )
                except asyncio.TimeoutError:
                    break
                try:
                    message = json.loads(raw)
                except (json.JSONDecodeError, TypeError) as exc:
                    print(f"忽略无效服务端消息，连接保持：{exc}", flush=True)
                    continue
                if not isinstance(message, dict):
                    print("忽略非对象服务端消息，连接保持。", flush=True)
                    continue
                if message.get("type") != "exec":
                    continue
                request_id = message.get("request_id")
                if request_id is None:
                    print("忽略缺少 request_id 的执行请求，连接保持。", flush=True)
                    continue
                command = message.get("command")
                if not isinstance(command, str) or not command.strip():
                    result = self.error_result(2, "command must be a non-empty string")
                else:
                    try:
                        timeout = float(message.get("timeout") or 60)
                    except (TypeError, ValueError):
                        timeout = math.nan
                    if not math.isfinite(timeout) or timeout <= 0:
                        result = self.error_result(2, "timeout must be a positive finite number")
                    else:
                        try:
                            result = await asyncio.to_thread(
                                partial(
                                    self.run_command,
                                    command,
                                    message.get("shell"),
                                    min(timeout, self.remaining_seconds()),
                                )
                            )
                        except Exception as exc:
                            result = self.error_result(
                                127,
                                f"command execution failed without disconnecting: {exc}",
                            )
                await send_result(websocket, request_id, result,
                                  chunks_supported=chunks_supported)

            await websocket.close(code=1000, reason="local authorization expired")
            print("授权已到期，本地 agent 已断开。", flush=True)


def main() -> int:
    args = parse_args()
    target_id = args.id or generate_target_id()
    agent = TargetAgent(
        base_url=args.base_url,
        target_id=target_id,
        expires_in_minutes=args.minutes,
    )
    try:
        asyncio.run(agent.run())
        return 0
    except KeyboardInterrupt:
        print("\n已手动停止，本地 agent 已断开。", flush=True)
        return 130
    except asyncio.CancelledError:
        print("\n连接已取消，本地 agent 已断开。", flush=True)
        return 130
    except (OSError, websockets.WebSocketException) as exc:
        print(f"\n连接中断，本地 agent 已断开: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
