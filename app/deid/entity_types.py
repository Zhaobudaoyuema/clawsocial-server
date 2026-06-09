"""User-configurable entity type categories (stored in deid_settings)."""
from __future__ import annotations

import json
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.deid.settings_store import get_setting, set_setting

ENTITY_TYPES_SETTING_KEY = "entity_types"
BUILTIN_CODES = frozenset({"company", "person", "org"})
CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

DEFAULT_ENTITY_TYPES: list[dict[str, str]] = [
    {"code": "company", "label": "公司", "placeholder_prefix": "公司"},
    {"code": "person", "label": "姓名", "placeholder_prefix": "姓名"},
    {"code": "org", "label": "机构", "placeholder_prefix": "机构"},
]


def _parse(raw: str | None) -> list[dict[str, str]]:
    if not raw:
        return [dict(t) for t in DEFAULT_ENTITY_TYPES]
    try:
        data = json.loads(raw)
        if isinstance(data, list) and data:
            out: list[dict[str, str]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("code") or "").strip()
                label = str(item.get("label") or "").strip()
                prefix = str(item.get("placeholder_prefix") or label or "实体").strip()
                if code and label:
                    out.append({"code": code, "label": label, "placeholder_prefix": prefix})
            if out:
                return out
    except json.JSONDecodeError:
        pass
    return [dict(t) for t in DEFAULT_ENTITY_TYPES]


def _save(db: Session, types: list[dict[str, str]]) -> None:
    set_setting(db, ENTITY_TYPES_SETTING_KEY, json.dumps(types, ensure_ascii=False))


def ensure_default_entity_types(db: Session) -> None:
    if get_setting(db, ENTITY_TYPES_SETTING_KEY) is None:
        _save(db, [dict(t) for t in DEFAULT_ENTITY_TYPES])


def list_entity_types(db: Session) -> list[dict[str, str]]:
    ensure_default_entity_types(db)
    return _parse(get_setting(db, ENTITY_TYPES_SETTING_KEY))


def get_type_map(db: Session) -> dict[str, dict[str, str]]:
    return {t["code"]: t for t in list_entity_types(db)}


def valid_codes(db: Session) -> set[str]:
    return set(get_type_map(db).keys())


def get_placeholder_prefix(db: Session, code: str) -> str:
    t = get_type_map(db).get(code)
    if t:
        return t.get("placeholder_prefix") or t.get("label") or "实体"
    return "实体"


def get_type_label(db: Session, code: str) -> str:
    t = get_type_map(db).get(code)
    return t.get("label", code) if t else code


def create_entity_type(db: Session, code: str, label: str, placeholder_prefix: str) -> dict[str, str]:
    ensure_default_entity_types(db)
    code = code.strip().lower()
    label = label.strip()
    placeholder_prefix = (placeholder_prefix or label).strip()
    if not CODE_RE.match(code):
        raise HTTPException(400, "分类代码须为小写字母开头，仅含 a-z、0-9、下划线")
    if not label:
        raise HTTPException(400, "显示名称不能为空")
    types = list_entity_types(db)
    if any(t["code"] == code for t in types):
        raise HTTPException(400, f"分类「{code}」已存在")
    row = {"code": code, "label": label, "placeholder_prefix": placeholder_prefix}
    types.append(row)
    _save(db, types)
    return row


def update_entity_type(
    db: Session,
    code: str,
    *,
    label: str | None = None,
    placeholder_prefix: str | None = None,
) -> dict[str, str]:
    ensure_default_entity_types(db)
    types = list_entity_types(db)
    for t in types:
        if t["code"] == code:
            if label is not None:
                label = label.strip()
                if not label:
                    raise HTTPException(400, "显示名称不能为空")
                t["label"] = label
            if placeholder_prefix is not None:
                prefix = placeholder_prefix.strip()
                if not prefix:
                    raise HTTPException(400, "占位前缀不能为空")
                t["placeholder_prefix"] = prefix
            _save(db, types)
            return dict(t)
    raise HTTPException(404, "分类不存在")


def delete_entity_type(db: Session, code: str) -> None:
    if code in BUILTIN_CODES:
        raise HTTPException(400, "内置分类不可删除，可修改显示名称")
    ensure_default_entity_types(db)
    types = list_entity_types(db)
    if not any(t["code"] == code for t in types):
        raise HTTPException(404, "分类不存在")
    _save(db, [t for t in types if t["code"] != code])
