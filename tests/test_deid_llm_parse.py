"""Tests for LLM scan response parsing (line format + JSON fallback)."""
from app.deid.discovery.llm_parse import (
    clean_llm_output,
    parse_line_entities,
    parse_llm_entities,
)

ALLOWED = frozenset({"company", "person", "org", "id"})


def test_parse_line_format_english_type():
    text = "company|中国能源建设股份有限公司\nperson|张三"
    items, fmt = parse_llm_entities(text, ALLOWED)
    assert fmt == "line"
    assert len(items) == 2
    assert items[0]["canonical_name"] == "中国能源建设股份有限公司"
    assert items[0]["entity_type"] == "company"
    assert items[1]["entity_type"] == "person"


def test_parse_line_format_chinese_type():
    text = "公司|中国能源建设股份有限公司"
    items, fmt = parse_llm_entities(text, ALLOWED)
    assert fmt == "line"
    assert items[0]["entity_type"] == "company"


def test_parse_bare_company_name():
    text = "中国能源建设股份有限公司"
    items, fmt = parse_llm_entities(text, ALLOWED)
    assert fmt == "line"
    assert items[0]["entity_type"] == "company"


def test_parse_empty_marker():
    items, fmt = parse_llm_entities("无", ALLOWED)
    assert fmt == "none"
    assert items == []


def test_parse_line_with_aliases():
    text = "company|中国能源建设股份有限公司|中国能建|中能建"
    items, fmt = parse_llm_entities(text, ALLOWED)
    assert fmt == "line"
    assert len(items) == 1
    assert items[0]["canonical_name"] == "中国能源建设股份有限公司"
    assert set(items[0]["aliases"]) == {
        "中国能源建设股份有限公司",
        "中国能建",
        "中能建",
    }


def test_parse_strips_thinking_blocks():
    open_tag = "<" + "think" + ">"
    close_tag = "<" + "/" + "think" + ">"
    raw = f"{open_tag}分析中…{close_tag}\ncompany|测试公司"
    cleaned = clean_llm_output(raw)
    assert "分析中" not in cleaned
    items, fmt = parse_llm_entities(raw, ALLOWED)
    assert fmt == "line"
    assert items[0]["canonical_name"] == "测试公司"


def test_json_fallback():
    text = '{"entities":[{"canonical_name":"某某公司","entity_type":"company"}]}'
    items, fmt = parse_llm_entities(text, ALLOWED)
    assert fmt == "json"
    assert items[0]["canonical_name"] == "某某公司"


def test_parse_comma_separated_names_as_multiple_entities():
    text = "company|能建YK07, 244323.SH, 25中能建MTN001, 25能建K1, 中国能建, 中能建"
    items, fmt = parse_llm_entities(text, ALLOWED)
    assert fmt == "line"
    assert len(items) == 6
    names = {i["canonical_name"] for i in items}
    assert "能建YK07" in names
    assert "244323.SH" in names
    assert "25中能建MTN001" in names
    assert "中国能建" in names
    assert "中能建" in names


def test_parse_rejects_invalid_dash_entity():
    text = "company|--\ncompany|测试公司"
    items, fmt = parse_llm_entities(text, ALLOWED)
    assert fmt == "line"
    assert len(items) == 1
    assert items[0]["canonical_name"] == "测试公司"

