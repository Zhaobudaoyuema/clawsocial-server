"""Dev relay token derived from machine identity — no server .env required.

Local Windows reads MachineGuid; server validates against ALLOWED_DEV_MACHINE_GUIDS
in this file. Only listed machines can produce a valid token.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import sys

logger = logging.getLogger(__name__)

RELAY_SALT = "clawsocial-deid-relay-v1"

# Registered dev workstations (lowercase GUID). Add yours via:
#   python -m scripts.show_dev_relay_token
ALLOWED_DEV_MACHINE_GUIDS: frozenset[str] = frozenset(
    {
        "a37709f3-72b1-41c0-b5db-fd17914df718",  # primary Windows dev (2026-06)
    }
)

DEFAULT_RELAY_URL = "https://clawsocial.world"


def token_from_machine_guid(guid: str) -> str:
    normalized = guid.strip().lower()
    payload = f"{RELAY_SALT}:{normalized}".encode()
    return hashlib.sha256(payload).hexdigest()


def is_allowed_relay_token(token: str) -> bool:
    if not token:
        return False
    for guid in ALLOWED_DEV_MACHINE_GUIDS:
        if token == token_from_machine_guid(guid):
            return True
    return False


def read_local_machine_guid() -> str | None:
    """Best-effort stable machine id for dev token generation."""
    system = platform.system()
    try:
        if system == "Windows":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                return str(value).strip() or None
        if system == "Linux":
            for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                try:
                    text = open(path, encoding="utf-8").read().strip()
                    if text:
                        return text
                except OSError:
                    continue
        if system == "Darwin":
            import subprocess

            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2].strip() or None
    except Exception as exc:
        logger.debug("read_local_machine_guid failed: %s", exc)
    return None


def get_local_dev_relay_token() -> str | None:
    guid = read_local_machine_guid()
    if not guid:
        return None
    if guid.lower() not in ALLOWED_DEV_MACHINE_GUIDS:
        return None
    return token_from_machine_guid(guid)


def resolve_dev_relay_token() -> str:
    explicit = os.getenv("DEID_WORKER_RELAY_TOKEN", "").strip()
    if explicit:
        return explicit
    return get_local_dev_relay_token() or ""


def resolve_dev_relay_url() -> str:
    explicit = os.getenv("DEID_WORKER_RELAY_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    if get_local_dev_relay_token():
        return DEFAULT_RELAY_URL
    return ""


def relay_allowlist_configured() -> bool:
    return bool(ALLOWED_DEV_MACHINE_GUIDS)


def describe_local_dev_machine() -> dict:
    guid = read_local_machine_guid()
    allowed = bool(guid and guid.lower() in ALLOWED_DEV_MACHINE_GUIDS)
    return {
        "machine_guid": guid,
        "registered": allowed,
        "relay_url": resolve_dev_relay_url() or None,
        "has_token": bool(get_local_dev_relay_token()),
        "platform": sys.platform,
    }
