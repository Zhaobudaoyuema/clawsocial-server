"""Parse LLM scan responses — line format first, JSON fallback."""
from __future__ import annotations

import json
import re

_LINE_SEP = re.compile(r"^[\s\-*•\d.)]+")
_TYPE_NAME = re.compile(
    r"^(?P<type>[a-z][a-z0-9_]{0,31}|[\u4e00-\u9fff]{1,8})\s*[|｜:：\t]\s*(?P<name>.+)$",
    re.IGNORECASE,
)
_COMPANY_HINT = re.compile(
    r"[\u4e00-\u9fff].*(?:公司|集团|有限|股份|银行|事务所|中心|研究院|大学|合伙)",
)
_NAME_SPLIT = re.compile(r"[,，、;；]")
_INVALID_LITERALS = frozenset(
    {
        "--",
        "---",
        "—",
        "–",
        "-",
        "…",
        "...",
        "无",
        "无实体",
        "none",
        "n/a",
        "null",
        "占位",
    }
)


def _clean_name(raw: str) -> str:
    return raw.strip().strip("\"'「」『』")


def is_invalid_entity_name(name: str) -> bool:
    n = _clean_name(name)
    if not n or len(n) < 2 or len(n) > 200:
        return True
    if n.casefold() in _INVALID_LITERALS:
        return True
    if re.fullmatch(r"[\-—–~·\.]+", n):
        return True
    return False


def _split_name_segments(text: str) -> list[str]:
    parts = [_clean_name(p) for p in _NAME_SPLIT.split(text) if _clean_name(p)]
    return [p for p in parts if not is_invalid_entity_name(p)]


def _pick_canonical(names: list[str]) -> tuple[str, list[str]]:
    cleaned = [n for n in (_clean_name(x) for x in names) if n and not is_invalid_entity_name(n)]
    if not cleaned:
        return "", []
    canonical = max(cleaned, key=len)
    aliases: list[str] = []
    for n in cleaned:
        if n not in aliases:
            aliases.append(n)
    return canonical, aliases


def _entity_dict(canonical: str, etype: str, aliases: list[str] | None = None) -> dict:
    alias_list = aliases or [canonical]
    if canonical not in alias_list:
        alias_list = [canonical, *alias_list]
    return {
        "canonical_name": canonical,
        "entity_type": etype,
        "aliases": alias_list,
    }


def _parse_pipe_line(line: str, allowed_types: frozenset[str]) -> list[dict]:
    """Parse type|name|alias1|alias2 …; comma-separated names become separate entities."""
    parts = [p.strip() for p in re.split(r"[|｜]", line) if p.strip()]
    if len(parts) < 2:
        return []
    etype = _normalize_type(parts[0], allowed_types)
    name_parts = parts[1:]

    if any("," in p or "，" in p or "、" in p for p in name_parts):
        out: list[dict] = []
        for part in name_parts:
            if _NAME_SPLIT.search(part):
                for seg in _split_name_segments(part):
                    out.append(_entity_dict(seg, etype))
            elif not is_invalid_entity_name(part):
                out.append(_entity_dict(_clean_name(part), etype))
        return out

    canonical, aliases = _pick_canonical(name_parts)
    if not canonical:
        return []
    return [_entity_dict(canonical, etype, aliases)]


def clean_llm_output(text: str) -> str:
    """Remove thinking blocks and markdown wrappers common in small models."""
    t = text.strip()
    for tag in ("think", "redacted_reasoning"):
        open_pat = re.compile(
            "(?is)" + re.escape("<") + tag + r"[^>]*>.*?" + re.escape("<") + "/" + tag + re.escape(">")
        )
        t = open_pat.sub("", t)
        t = re.sub("(?is)" + re.escape("<") + tag + r"[^>]*/?>", "", t)
    t = re.sub(r"```(?:json|text|plaintext)?\s*([\s\S]*?)```", r"\1", t, flags=re.IGNORECASE)
    return t.strip()


def _normalize_type(raw: str, allowed: frozenset[str]) -> str:
    code = raw.strip().lower()
    aliases = {
        "公司": "company",
        "企业": "company",
        "姓名": "person",
        "人名": "person",
        "人员": "person",
        "机构": "org",
        "组织": "org",
        "证件": "id",
        "身份证": "id",
        "信用代码": "id",
    }
    if code in aliases:
        code = aliases[code]
    if code in allowed:
        return code
    if "company" in allowed:
        return "company"
    return next(iter(allowed))


def _append_entity(
    out: list[dict],
    seen: set[str],
    etype: str,
    name: str,
    alias_list: list[str] | None = None,
    *,
    allowed_types: frozenset[str],
) -> None:
    if _NAME_SPLIT.search(name):
        for seg in _split_name_segments(name):
            _append_entity(out, seen, etype, seg, allowed_types=allowed_types)
        return
    name = _clean_name(name)
    if is_invalid_entity_name(name):
        return
    etype = etype or _normalize_type("company", allowed_types)
    aliases = [a for a in (alias_list or [name]) if not is_invalid_entity_name(a)]
    if name not in aliases:
        aliases = [name, *aliases]
    key = name.casefold()
    if key in seen:
        return
    seen.add(key)
    out.append(_entity_dict(name, etype, aliases))


def parse_line_entities(content: str, allowed_types: frozenset[str]) -> list[dict]:
    """Parse `type|name` lines; tolerate Chinese type labels and bare company names."""
    cleaned = clean_llm_output(content)
    if not cleaned:
        return []
    if cleaned in {"无", "无实体", "none", "NONE", "N/A", "无。"}:
        return []

    out: list[dict] = []
    seen: set[str] = set()

    for raw_line in cleaned.splitlines():
        line = _LINE_SEP.sub("", raw_line.strip())
        if not line or line.startswith("#"):
            continue
        if line in {"无", "无实体", "none"}:
            continue

        etype: str | None = None
        name: str | None = None
        alias_list: list[str] = []
        m = _TYPE_NAME.match(line)
        if m:
            etype = _normalize_type(m.group("type"), allowed_types)
            rest = m.group("name").strip()
            if "|" in rest or "｜" in rest:
                for item in _parse_pipe_line(line, allowed_types):
                    _append_entity(
                        out,
                        seen,
                        item["entity_type"],
                        item["canonical_name"],
                        item["aliases"],
                        allowed_types=allowed_types,
                    )
                continue
            name = rest
            alias_list = [name]
        else:
            if "|" in line or "｜" in line:
                items = _parse_pipe_line(line, allowed_types)
                if items:
                    for item in items:
                        _append_entity(
                            out,
                            seen,
                            item["entity_type"],
                            item["canonical_name"],
                            item["aliases"],
                            allowed_types=allowed_types,
                        )
                    continue
                for sep in ("|", "｜", "：", ":"):
                    if sep in line:
                        left, right = line.split(sep, 1)
                        if left.strip() and right.strip():
                            etype = _normalize_type(left, allowed_types)
                            name = right.strip()
                            alias_list = [name]
                        break
            else:
                for sep in ("|", "｜", "：", ":"):
                    if sep in line:
                        left, right = line.split(sep, 1)
                        if left.strip() and right.strip():
                            etype = _normalize_type(left, allowed_types)
                            name = right.strip()
                            alias_list = [name]
                        break

        if not name and _COMPANY_HINT.search(line) and len(line) <= 80:
            etype = "company" if "company" in allowed_types else _normalize_type("company", allowed_types)
            name = line.strip()
            alias_list = [name]

        if not name:
            continue
        _append_entity(
            out,
            seen,
            etype or _normalize_type("company", allowed_types),
            name,
            alias_list,
            allowed_types=allowed_types,
        )

    return out


def parse_json_entities(content: str) -> list[dict]:
    cleaned = clean_llm_output(content)
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", cleaned)
    if brace:
        cleaned = brace.group(0)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    items = parsed.get("entities") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict)]


def parse_llm_entities(content: str, allowed_types: frozenset[str]) -> tuple[list[dict], str]:
    """Returns (entities, format_used). format_used: line|json|none"""
    cleaned = clean_llm_output(content).strip()
    if cleaned.startswith("{") or cleaned.startswith("[") or '"entities"' in cleaned:
        json_items = parse_json_entities(content)
        if json_items:
            return json_items, "json"

    line_items = parse_line_entities(content, allowed_types)
    if line_items:
        return line_items, "line"
    json_items = parse_json_entities(content)
    if json_items:
        return json_items, "json"
    return [], "none"
