"""Standalone controlled-computer agent for ClawSocial remote commands.

Run this script on the controlled computer. It registers a short-lived target id
with the relay server, prints the authorization id, then keeps a WebSocket
connection open until the local authorization window expires. This is intended
to run in the foreground; closing the terminal window disconnects the target.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import secrets
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import websockets


DEFAULT_BASE_URL = "http://clawsocial.world"
DEFAULT_EXPIRES_IN_MINUTES = 180
ALLOWED_EXPIRES_IN_MINUTES = {10, 30, 180}
BLOCKED_COMMAND_MARKERS = [
    "taskkill",
    "schtasks",
    "reg add",
    "reg delete",
    "format ",
    "del ",
    "rmdir ",
]


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

    def is_blocked_command(self, command: str) -> bool:
        lowered = command.lower()
        return any(marker in lowered for marker in BLOCKED_COMMAND_MARKERS)

    def run_command(self, command: str, shell_name: str | None, timeout: float) -> dict:
        if self.remaining_seconds() <= 0:
            return self.error_result(125, "local authorization expired")
        if self.is_blocked_command(command):
            return self.error_result(126, "blocked by local target policy")

        shell_name = shell_name or "cmd"
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
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "exit_code": 124,
                "stdout": exc.stdout or "",
                "stderr": "command timed out",
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
        print("把上面的授权 id 发给操作者。保持这个窗口打开。")
        print("这个脚本必须前台运行；关闭 CMD/PowerShell 窗口后，被操作者会立刻离线。")
        print("=" * 64, flush=True)

        async with websockets.connect(self.ws_url()) as websocket:
            registered_message = await websocket.recv()
            print(f"已连接服务端: {registered_message}", flush=True)
            await websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "target_id": self.target_id,
                        "hostname": platform.node(),
                        "platform": platform.platform(),
                        "shell": "cmd",
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
                message = json.loads(raw)
                if message.get("type") != "exec":
                    continue
                result = self.run_command(
                    message["command"],
                    message.get("shell"),
                    min(float(message.get("timeout") or 60), self.remaining_seconds()),
                )
                result.update({"type": "result", "request_id": message["request_id"]})
                await websocket.send(json.dumps(result, ensure_ascii=False))

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
    asyncio.run(agent.run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
