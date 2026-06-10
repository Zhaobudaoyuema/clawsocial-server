"""Semantic rewrite fallbacks and validation (Worker-first detect)."""
from __future__ import annotations

import os
import re
import uuid

from app.deid.discovery.semantic_categories import LEGACY_CATEGORY_MAP, normalize_category
from app.deid.engine.plan import normalize_for_match

_STOCK_CODE = re.compile(r"^\d{6}\.[A-Z]{2,4}$", re.I)
_LISTING_AH = re.compile(r"上市公司.*[AH＋+]|流通A股.*流通H股|流通H股")

CATEGORY_REWRITE_FALLBACK: dict[str, str] = {
    "project_id": "内控审计项目",
    "project_name": "新能源示范项目",
    "listing_code": "证券代码",
    "listing_structure": "多市场上市",
    "data_source": "外部数据源",
    "deal_event": "关联交易事项",
    "client_hint": "非上市主体",
    "table_row": "某地区",
}

_DATA_SOURCE_TERMS = (
    (re.compile(r"同花顺"), "外部数据源"),
    (re.compile(r"(?i)wind"), "外部数据源"),
)
_PROJECT_ID = re.compile(r"\d{6}.+?内控(?:审计)?")
_DATA_SOURCE_LINE = re.compile(r"当前数据来源：[^\n]{1,40}")
_CLIENT_HINTS = (
    (re.compile(r"非公开上市企业"), "非上市主体"),
)


def program_rules_enabled() -> bool:
    return os.getenv("DEID_SEMANTIC_PROGRAM_RULES", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _make_risk(
    *,
    category: str,
    original: str,
    rewritten: str,
    note: str = "",
) -> dict:
    return {
        "risk_id": f"r-prog-{uuid.uuid4().hex[:8]}",
        "category": category,
        "original": original,
        "note": note,
        "source": "program",
        "enabled": True,
        "suggested_rewrite": rewritten,
        "rewritten": rewritten,
        "writable": "\n" not in original and "\r" not in original,
    }


def extract_program_risks(preview_text: str) -> list[dict]:
    """Legacy deterministic detect — disabled by default (DEID_SEMANTIC_PROGRAM_RULES=1)."""
    if not program_rules_enabled() or not preview_text:
        return []
    risks: list[dict] = []
    seen: set[str] = set()

    def add(category: str, original: str, rewritten: str, note: str = "") -> None:
        if not original or not rewritten or original == rewritten:
            return
        key = normalize_for_match(f"{category}\0{original}")
        if key in seen:
            return
        seen.add(key)
        item = _make_risk(category=category, original=original, rewritten=rewritten, note=note)
        item["writable"] = original in preview_text and "\n" not in original
        risks.append(item)

    for pat, repl in _DATA_SOURCE_TERMS:
        for m in pat.finditer(preview_text):
            add("data_source", m.group(0), repl, "数据来源平台")

    for m in _PROJECT_ID.finditer(preview_text):
        add("project_id", m.group(0), "内控审计项目", "项目编号指纹")

    for pat, repl in _CLIENT_HINTS:
        for m in pat.finditer(preview_text):
            add("client_hint", m.group(0), repl, "客户分类提示")

    for m in _DATA_SOURCE_LINE.finditer(preview_text):
        add("data_source", m.group(0), "当前数据来源：外部数据源", "数据来源行")

    for m in re.finditer(r"\d{6}\.[A-Z]{2,4}", preview_text):
        add("listing_code", m.group(0), "证券代码", "证券代码")

    return risks


def merge_program_and_worker_risks(
    program: list[dict],
    worker: list[dict],
) -> list[dict]:
    """Merge risks; program entries win on normalized original collision."""
    out: list[dict] = list(program)
    prog_keys = {
        normalize_for_match(r.get("original") or "")
        for r in program
        if r.get("original")
    }
    for item in worker:
        orig = item.get("original") or ""
        key = normalize_for_match(orig)
        if key and key in prog_keys:
            continue
        out.append(item)
    return out


def default_semantic_rewrite(category: str, original: str) -> str | None:
    """Deterministic rewrite fallback when Worker suggest fails."""
    s = original.strip()
    if not s:
        return None
    cat = normalize_category(category)

    fallback = CATEGORY_REWRITE_FALLBACK.get(cat)
    if fallback and fallback != s:
        if cat == "project_id" and re.search(r"内控", s):
            return "内控审计项目"
        if cat == "listing_code" and _STOCK_CODE.match(s.replace(" ", "")):
            return "证券代码"
        if cat == "data_source":
            if "当前数据来源" in s:
                out = re.sub(r"同花顺|wind", "外部数据源", s, flags=re.I)
                return out if out != s else "当前数据来源：外部数据源"
            if re.search(r"同花顺|wind", s, flags=re.I):
                return "外部数据源"
        if cat == "client_hint" and "非公开上市" in s:
            return "非上市主体"
        if cat == "listing_structure" and _LISTING_AH.search(s):
            return "多市场上市"
        if cat in ("project_name", "deal_event", "table_row"):
            return fallback
        if cat == "listing_code":
            return "证券代码"
        return fallback

    # Legacy category support
    legacy = LEGACY_CATEGORY_MAP.get((category or "").strip().lower())
    if legacy:
        return default_semantic_rewrite(legacy, original)

    return None


def apply_default_rewrites(risks: list[dict]) -> list[dict]:
    """Fill suggested_rewrite from fallbacks; skip items that already have one."""
    out: list[dict] = []
    for risk in risks:
        item = dict(risk)
        if item.get("category"):
            item["category"] = normalize_category(str(item["category"]))
        if item.get("suggested_rewrite") or item.get("rewritten"):
            out.append(item)
            continue
        rewrite = default_semantic_rewrite(
            str(item.get("category") or ""),
            str(item.get("original") or ""),
        )
        if rewrite and rewrite != item.get("original"):
            item["suggested_rewrite"] = rewrite
            item["rewritten"] = rewrite
            if not item.get("source"):
                item["source"] = "rule"
        out.append(item)
    return out


def validate_suggest_rewrite(category: str, original: str, rewrite: str) -> bool:
    """Reject LLM rewrites that expand, leak, or fail to generalize."""
    s = original.strip()
    r = rewrite.strip()
    if not r or r == s:
        return False
    if len(r) > len(s) * 1.4 + 16:
        return False
    if ("；" in r or ";" in r) and "；" not in s and ";" not in s:
        return False
    cat = normalize_category(category)
    if cat == "data_source" and re.search(r"同花顺|wind", r, flags=re.I):
        return False
    if cat == "listing_code" and _STOCK_CODE.match(s.replace(" ", "")):
        if r == s:
            return False
        if re.search(r"\d{6}", r):
            return False
        if re.search(r"[\u4e00-\u9fff]{2,}", r) and "证券" not in r and "代码" not in r:
            return False
    if cat == "project_name" and re.search(r"哈密|应城|乌兹别克|光热|MW", r, flags=re.I):
        return False
    if re.search(r"同花顺|wind", r, flags=re.I) and not re.search(r"同花顺|wind", s, flags=re.I):
        return False
    return True
