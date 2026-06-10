"""Semantic fingerprint category constants and labels."""
from __future__ import annotations

RISK_CATEGORIES = frozenset(
    {
        "project_id",
        "project_name",
        "listing_code",
        "listing_structure",
        "data_source",
        "deal_event",
        "person_trait",
        "client_hint",
        "table_row",
    }
)

CAT_LABELS: dict[str, str] = {
    "project_id": "项目编号",
    "project_name": "具名项目",
    "listing_code": "证券代码",
    "listing_structure": "上市结构",
    "data_source": "数据来源",
    "deal_event": "交易事件",
    "person_trait": "人员属性",
    "client_hint": "客户线索",
    "table_row": "表行短语",
}

LEGACY_CATEGORY_MAP: dict[str, str] = {
    "org_fingerprint": "table_row",
    "person_fingerprint": "person_trait",
    "listing_fingerprint": "listing_code",
}

HIGH_RISK_CATEGORIES = frozenset(
    {
        "project_id",
        "project_name",
        "listing_code",
        "deal_event",
        "data_source",
    }
)


def normalize_category(category: str | None) -> str:
    cat = (category or "").strip().lower()
    return LEGACY_CATEGORY_MAP.get(cat, cat)


def cat_label(category: str | None) -> str:
    cat = normalize_category(category)
    return CAT_LABELS.get(cat, cat or "语义")


def migrate_risk_category(risk: dict) -> dict:
    """Return copy with legacy category mapped to v5."""
    out = dict(risk)
    raw = out.get("category")
    if raw:
        out["category"] = normalize_category(str(raw))
    return out
