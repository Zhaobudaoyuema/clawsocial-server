"""Parse Mac Worker flow responses — line format per flow type."""
from __future__ import annotations

import re

from app.deid.discovery.llm_parse import _LINE_SEP, _clean_name, clean_llm_output

_SURFACE_PREFIX = re.compile(r"^surface\s*[|｜]", re.IGNORECASE)
_LEAK_PREFIX = re.compile(r"^leak\s*[|｜]", re.IGNORECASE)
_RISK_PREFIX = re.compile(r"^risk\s*[|｜]", re.IGNORECASE)
_SUGGEST_PREFIX = re.compile(r"^suggest\s*[|｜]", re.IGNORECASE)
_READY_PREFIX = re.compile(r"^ready\s*[|｜]", re.IGNORECASE)
_BLOCKER_PREFIX = re.compile(r"^blocker\s*[|｜]", re.IGNORECASE)
_NOTE_PREFIX = re.compile(r"^note\s*[|｜]", re.IGNORECASE)

from app.deid.discovery.semantic_categories import RISK_CATEGORIES, normalize_category

_RISK_CATEGORIES = RISK_CATEGORIES
_LEAK_CATEGORIES = frozenset({"entity_leak", "metadata_leak"})
_EXP_PREFIX = re.compile(r"^exp\s*[|｜]", re.IGNORECASE)


def _split_pipe(line: str) -> list[str]:
    return [p.strip() for p in re.split(r"[|｜]", line) if p.strip()]


def _is_none_line(line: str) -> bool:
    return line.strip().lower() in {"无", "无实体", "none", "n/a", "无。"}


def parse_surface_lines(content: str) -> list[dict]:
    """Parse `surface|canonical|文档写法` lines."""
    cleaned = clean_llm_output(content)
    out: list[dict] = []
    seen: set[str] = set()
    for raw in cleaned.splitlines():
        line = _LINE_SEP.sub("", raw.strip())
        if not line or _is_none_line(line) or not _SURFACE_PREFIX.match(line):
            continue
        parts = _split_pipe(line)
        if len(parts) < 3:
            continue
        canonical = _clean_name(parts[1])
        surface = _clean_name(parts[2])
        if not canonical or not surface or canonical == surface:
            continue
        key = f"{canonical.casefold()}\0{surface.casefold()}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"canonical": canonical, "surface": surface})
    return out


def parse_exp_lines(content: str) -> list[str]:
    """Parse `exp|抽象经验` lines; dedupe; skip 无."""
    cleaned = clean_llm_output(content)
    out: list[str] = []
    seen: set[str] = set()
    for raw in cleaned.splitlines():
        line = _LINE_SEP.sub("", raw.strip())
        if not line or _is_none_line(line):
            continue
        if not _EXP_PREFIX.match(line):
            continue
        parts = _split_pipe(line)
        if len(parts) < 2:
            continue
        text = parts[1].strip()
        if not text or _is_none_line(text):
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def parse_leak_lines(content: str) -> list[dict]:
    """Parse `leak|类别|片段|说明` lines."""
    cleaned = clean_llm_output(content)
    out: list[dict] = []
    for raw in cleaned.splitlines():
        line = _LINE_SEP.sub("", raw.strip())
        if not line or _is_none_line(line) or not _LEAK_PREFIX.match(line):
            continue
        parts = _split_pipe(line)
        if len(parts) < 3:
            continue
        category = parts[1].strip().lower()
        if category not in _LEAK_CATEGORIES:
            continue
        snippet = _clean_name(parts[2])
        note = _clean_name(parts[3]) if len(parts) > 3 else ""
        if not snippet:
            continue
        out.append({"category": category, "snippet": snippet, "note": note})
    return out


def parse_risk_lines(content: str) -> list[dict]:
    """Parse `risk|类别|原文逐字摘录|说明` lines."""
    cleaned = clean_llm_output(content)
    out: list[dict] = []
    for raw in cleaned.splitlines():
        line = _LINE_SEP.sub("", raw.strip())
        if not line or _is_none_line(line) or not _RISK_PREFIX.match(line):
            continue
        parts = _split_pipe(line)
        if len(parts) < 3:
            continue
        category = normalize_category(parts[1].strip())
        if category not in _RISK_CATEGORIES:
            continue
        original = parts[2]
        rewrite: str | None = None
        note = ""
        if len(parts) >= 5:
            rewrite = parts[3] or None
            note = parts[4]
        elif len(parts) == 4:
            note = parts[3]
        if not original:
            continue
        if rewrite in ("-", "—", "略", "无"):
            rewrite = None
        entry: dict = {
            "category": category,
            "original": original,
            "note": note,
        }
        if rewrite:
            entry["rewrite"] = rewrite
        out.append(entry)
    return out


def parse_suggest_line(content: str) -> str | None:
    """Parse single-line `suggest|改写后文本`."""
    cleaned = clean_llm_output(content)
    for raw in cleaned.splitlines():
        line = _LINE_SEP.sub("", raw.strip())
        if not line or _is_none_line(line):
            continue
        if not _SUGGEST_PREFIX.match(line):
            continue
        parts = _split_pipe(line)
        if len(parts) < 2:
            return None
        text = parts[1]
        return text if text else None
    return None


def parse_readiness_lines(content: str) -> dict:
    """Parse export_readiness flow output."""
    cleaned = clean_llm_output(content)
    result: dict = {"ready": None, "blockers": [], "notes": []}
    for raw in cleaned.splitlines():
        line = _LINE_SEP.sub("", raw.strip())
        if not line or _is_none_line(line):
            continue
        if _READY_PREFIX.match(line):
            parts = _split_pipe(line)
            if len(parts) >= 2:
                val = parts[1].strip().lower()
                result["ready"] = val in ("true", "1", "yes", "是")
        elif _BLOCKER_PREFIX.match(line):
            parts = _split_pipe(line)
            if len(parts) >= 2:
                result["blockers"].append(parts[1])
        elif _NOTE_PREFIX.match(line):
            parts = _split_pipe(line)
            if len(parts) >= 2:
                result["notes"].append(parts[1])
    return result
