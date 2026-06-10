"""Daily deid access: server-side day calculation + opaque session credentials."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import date, datetime, timedelta, timezone

_EPOCH = date(2023, 6, 8)
_BEIJING = timezone(timedelta(hours=8))


def beijing_today() -> date:
    return datetime.now(_BEIJING).date()


def current_deid_day_token() -> int:
    return (beijing_today() - _EPOCH).days


def validate_deid_day_code(code: str | int | None) -> bool:
    """Validate user-entered day code (only used by /access/verify)."""
    if code is None:
        return False
    try:
        value = int(str(code).strip())
    except (ValueError, TypeError):
        return False
    return value == current_deid_day_token()


def _secret() -> bytes:
    key = os.getenv("DEID_ACCESS_SECRET", "")
    if not key:
        key = "deid-access-dev-secret"
    return key.encode()


def issue_deid_access_session() -> str:
    """Opaque daily session; calculation stays server-side only."""
    today = beijing_today().isoformat()
    nonce = secrets.token_hex(12)
    payload = f"{today}:{nonce}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def validate_deid_access_session(credential: str | None) -> bool:
    """Validate opaque session issued after successful verify."""
    if not credential or not str(credential).strip():
        return False
    try:
        parts = str(credential).strip().split(":")
        if len(parts) != 3:
            return False
        today_str, _nonce, sig = parts
        if today_str != beijing_today().isoformat():
            return False
        payload = f"{parts[0]}:{parts[1]}"
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False
