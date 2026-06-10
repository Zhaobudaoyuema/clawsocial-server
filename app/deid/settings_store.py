"""Global deid settings (scan prompt, etc.)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.deid.prompts import (
    build_default_scan_prompt,
    EXPORT_FILENAME_MODE_KEY,
    FLOW_DEEP_DETECT_KEY,
    FLOW_PROMPT_DEFAULTS,
    SCAN_PROMPT_SETTING_KEY,
)
from app.models_deid import DeidSetting
from app.time_utils import coerce_beijing


def get_setting(db: Session, key: str) -> str | None:
    row = db.get(DeidSetting, key)
    return row.value if row else None


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(DeidSetting, key)
    if row:
        row.value = value
    else:
        db.add(DeidSetting(key=key, value=value))
    db.commit()


def get_scan_prompt(db: Session) -> str:
    stored = get_setting(db, SCAN_PROMPT_SETTING_KEY)
    if stored is not None and stored.strip():
        return stored.strip()
    return build_default_scan_prompt()


def ensure_default_scan_prompt(db: Session) -> None:
    if get_setting(db, SCAN_PROMPT_SETTING_KEY) is None:
        set_setting(db, SCAN_PROMPT_SETTING_KEY, build_default_scan_prompt())


def get_flow_prompt(db: Session, key: str) -> str:
    default = FLOW_PROMPT_DEFAULTS.get(key, "")
    stored = get_setting(db, key)
    if stored is not None and stored.strip():
        return stored.strip()
    return default


def ensure_flow_prompts(db: Session) -> None:
    ensure_default_scan_prompt(db)
    for key, default in FLOW_PROMPT_DEFAULTS.items():
        if get_setting(db, key) is None:
            set_setting(db, key, default)
    stored_detect = get_setting(db, FLOW_DEEP_DETECT_KEY) or ""
    if any(
        tag in stored_detect
        for tag in ("deep_detect_v1", "deep_detect_v2", "deep_detect_v3", "deep_detect_v4")
    ):
        set_setting(db, FLOW_DEEP_DETECT_KEY, FLOW_PROMPT_DEFAULTS[FLOW_DEEP_DETECT_KEY])
    if get_setting(db, EXPORT_FILENAME_MODE_KEY) is None:
        set_setting(db, EXPORT_FILENAME_MODE_KEY, "neutral")


def get_export_filename_mode(db: Session) -> str:
    mode = (get_setting(db, EXPORT_FILENAME_MODE_KEY) or "neutral").strip().lower()
    return mode if mode in ("neutral", "original_stem") else "neutral"


def reset_scan_prompt(db: Session) -> str:
    prompt = build_default_scan_prompt()
    set_setting(db, SCAN_PROMPT_SETTING_KEY, prompt)
    return prompt


def scan_prompt_meta(db: Session) -> dict:
    row = db.get(DeidSetting, SCAN_PROMPT_SETTING_KEY)
    updated_at = None
    if row and row.updated_at:
        c = coerce_beijing(row.updated_at)
        updated_at = c.isoformat() if c else None
    return {
        "prompt": get_scan_prompt(db),
        "default_prompt": build_default_scan_prompt(),
        "updated_at": updated_at,
    }
