"""Shared auth for DEID dev worker relay (server-side)."""
from __future__ import annotations

import os

from fastapi import HTTPException, Request

from app.deid.worker.dev_machine_token import (
    is_allowed_relay_token,
    relay_allowlist_configured,
)

TOKEN_ENV = "DEID_DEV_RELAY_TOKEN"
IPS_ENV = "DEID_DEV_RELAY_IPS"


def relay_enabled() -> bool:
    if os.getenv(TOKEN_ENV, "").strip():
        return True
    return relay_allowlist_configured()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    header = request.headers.get("X-Deid-Relay-Token")
    return header.strip() if header else None


def _token_is_valid(token: str | None) -> bool:
    if not token:
        return False
    expected = os.getenv(TOKEN_ENV, "").strip()
    if expected and token == expected:
        return True
    return is_allowed_relay_token(token)


def verify_relay_auth(request: Request) -> None:
    """Raise HTTPException if relay token or IP check fails."""
    if not relay_enabled():
        raise HTTPException(status_code=404, detail="not_found")

    token = _extract_token(request)
    if not _token_is_valid(token):
        raise HTTPException(status_code=401, detail="relay_token_invalid")

    allowlist = os.getenv(IPS_ENV, "").strip()
    if allowlist:
        allowed = {ip.strip() for ip in allowlist.split(",") if ip.strip()}
        client_ip = _client_ip(request)
        if client_ip not in allowed:
            raise HTTPException(status_code=403, detail="relay_ip_denied")
