"""HTTP client: local dev server → remote production Mac Worker relay."""
from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.deid.worker.dev_machine_token import resolve_dev_relay_token, resolve_dev_relay_url
from app.deid.worker.errors import WorkerBusy, WorkerOffline, WorkerRequestError

logger = logging.getLogger(__name__)

URL_ENV = "DEID_WORKER_RELAY_URL"
TOKEN_ENV = "DEID_WORKER_RELAY_TOKEN"
STATUS_TTL_SEC = 8.0


@dataclass
class RelaySessionView:
    hostname: str = ""
    model: str = ""
    version: str = ""
    mode: str = "relay"
    state: str = "offline"
    remote_ip: str | None = None

    @property
    def online(self) -> bool:
        return self.state not in ("offline", "")


class RemoteWorkerRelay:
    """Proxy WorkerRouter calls to a remote server's /api/deid/dev/worker/* endpoints."""

    def __init__(self) -> None:
        self._base_url = ""
        self._token = ""
        self._status: dict[str, Any] | None = None
        self._status_at = 0.0
        self._sync_config()

    def _sync_config(self) -> None:
        self._base_url = resolve_dev_relay_url()
        self._token = resolve_dev_relay_token()

    @property
    def enabled(self) -> bool:
        self._sync_config()
        return bool(self._base_url and self._token)

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def session(self) -> RelaySessionView | None:
        if not self.enabled or not self._status or not self._status.get("online"):
            return None
        return RelaySessionView(
            hostname=str(self._status.get("hostname") or ""),
            model=str(self._status.get("model") or ""),
            version=str(self._status.get("version") or ""),
            mode=str(self._status.get("mode") or "relay"),
            state=str(self._status.get("state") or "offline"),
            remote_ip=self._status.get("remote_ip"),
        )

    def status_dict(self) -> dict[str, Any]:
        if self._status:
            return dict(self._status)
        return {
            "online": False,
            "state": "offline",
            "model": None,
            "hostname": None,
            "version": None,
            "mode": "relay",
            "relay_url": self._base_url or None,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def refresh_status(self) -> None:
        if not self.enabled:
            self._status = None
            return
        now = time.monotonic()
        if self._status is not None and now - self._status_at < STATUS_TTL_SEC:
            return
        url = f"{self._base_url}/api/deid/dev/worker/status"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=self._headers())
            if resp.status_code == 404:
                logger.warning("worker relay not enabled on remote server")
                self._status = {"online": False, "state": "offline", "relay_error": "relay_disabled"}
                self._status_at = now
                return
            resp.raise_for_status()
            self._status = resp.json()
            self._status_at = now
        except Exception as exc:
            logger.warning("worker relay status refresh failed: %s", exc)
            self._status = {
                "online": False,
                "state": "offline",
                "relay_error": type(exc).__name__,
            }
            self._status_at = now

    async def chat_completions(
        self,
        body: dict[str, Any],
        *,
        request_id: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise WorkerOffline("relay_not_configured")
        await self.refresh_status()
        if not self.session or self.session.state != "ready":
            raise WorkerOffline("worker_offline")

        url = f"{self._base_url}/api/deid/dev/worker/chat-completions"
        payload = {
            "body": body,
            "request_id": request_id,
            "timeout": timeout,
            "stream": False,
        }
        delay = 1.0
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout + 30.0) as client:
                    resp = await client.post(url, headers=self._headers(), json=payload)
            except httpx.TimeoutException as exc:
                raise WorkerRequestError(504, {"error": "timeout"}) from exc
            except httpx.HTTPError as exc:
                last_err = exc
                raise WorkerOffline("relay_unreachable") from exc

            if resp.status_code == 401:
                raise WorkerOffline("relay_token_invalid")
            if resp.status_code == 403:
                raise WorkerOffline("relay_ip_denied")
            if resp.status_code == 429 and attempt < max_retries - 1:
                await _sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 503:
                raise WorkerOffline("worker_offline")
            if resp.status_code >= 400:
                try:
                    detail = resp.json()
                except Exception:
                    detail = {"error": resp.text}
                raise WorkerRequestError(resp.status_code, detail)

            data = resp.json()
            return data.get("body") or {}

        if last_err:
            raise last_err
        raise WorkerRequestError(429, {"error": "worker_busy"})

    async def chat_completions_stream(
        self,
        body: dict[str, Any],
        *,
        request_id: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> AsyncIterator[str]:
        if not self.enabled:
            raise WorkerOffline("relay_not_configured")
        await self.refresh_status()
        if not self.session or self.session.state != "ready":
            raise WorkerOffline("worker_offline")

        url = f"{self._base_url}/api/deid/dev/worker/chat-completions"
        payload = {
            "body": {**body, "stream": True},
            "request_id": request_id,
            "timeout": timeout,
            "stream": True,
        }
        delay = 1.0
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout + 30.0) as client:
                    async with client.stream(
                        "POST", url, headers=self._headers(), json=payload
                    ) as resp:
                        if resp.status_code == 429 and attempt < max_retries - 1:
                            await _sleep(delay)
                            delay *= 2
                            continue
                        if resp.status_code == 503:
                            raise WorkerOffline("worker_offline")
                        if resp.status_code >= 400:
                            text = await resp.aread()
                            raise WorkerRequestError(resp.status_code, {"error": text.decode()})
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if not raw:
                                continue
                            try:
                                msg = json.loads(raw)
                            except json.JSONDecodeError:
                                continue
                            if msg.get("done"):
                                return
                            if "error" in msg:
                                raise WorkerRequestError(502, msg)
                            token = msg.get("token")
                            if token:
                                yield str(token)
                        return
            except WorkerOffline:
                raise
            except WorkerRequestError:
                raise
            except httpx.TimeoutException as exc:
                raise WorkerRequestError(504, {"error": "timeout"}) from exc
            except httpx.HTTPError as exc:
                raise WorkerOffline("relay_unreachable") from exc
        raise WorkerRequestError(429, {"error": "worker_busy"})


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


async def bootstrap_worker_relay(relay: RemoteWorkerRelay) -> None:
    """On app startup: refresh remote worker status and log how LLM will be reached."""
    if not relay.enabled:
        from app.deid.worker.dev_machine_token import describe_local_dev_machine

        info = describe_local_dev_machine()
        if info.get("machine_guid") and not info.get("registered"):
            logger.warning(
                "DEID: 本机 MachineGuid 未在白名单，Worker/LLM 不可用（仅词库+规则）"
            )
        else:
            logger.info("DEID: 等待本机 Mac Worker 连接 /ws/worker")
        return

    await relay.refresh_status()
    st = relay.status_dict()
    if st.get("online"):
        logger.info(
            "DEID: 使用远程 Mac Worker → %s | %s (%s)",
            relay.base_url,
            st.get("model") or "?",
            st.get("hostname") or "?",
        )
    else:
        logger.warning(
            "DEID: 远程 Worker 中继已启用 (%s)，但生产 Mac Worker 当前离线",
            relay.base_url,
        )


def probe_worker_relay_sync() -> None:
    """Sync probe for run.py startup banner (before uvicorn)."""
    from app.deid.worker.dev_machine_token import (
        describe_local_dev_machine,
        resolve_dev_relay_token,
        resolve_dev_relay_url,
    )

    info = describe_local_dev_machine()
    if not info.get("has_token"):
        if info.get("machine_guid") and not info.get("registered"):
            logger.warning(
                "[Worker] 本机 GUID 未注册，扫描无 LLM。运行: python -m scripts.show_dev_relay_token"
            )
        return

    url = resolve_dev_relay_url()
    logger.info("[Worker] 本地启动 → 远程中继 %s", url)
    token = resolve_dev_relay_token()
    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.get(
                f"{url}/api/deid/dev/worker/status",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code != 200:
            logger.warning("[Worker] 中继探测失败 HTTP %s", resp.status_code)
            return
        st = resp.json()
        if st.get("online"):
            logger.info(
                "[Worker] 远程 Mac Worker 就绪: %s @ %s",
                st.get("model") or "?",
                st.get("hostname") or "?",
            )
        else:
            logger.warning("[Worker] 远程 Mac Worker 离线 (state=%s)", st.get("state"))
    except Exception as exc:
        logger.warning("[Worker] 中继探测失败: %s", exc)

