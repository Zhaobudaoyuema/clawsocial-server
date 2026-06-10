"""Tests for Worker flow parsers and executor helpers."""
from app.deid.discovery.flow_parse import (
    parse_leak_lines,
    parse_readiness_lines,
    parse_risk_lines,
    parse_suggest_line,
    parse_surface_lines,
)
from app.deid.discovery.flows import FlowItem, flow_items_from_text_chunks


def test_parse_surface_lines():
    text = "surface|中国能源建设集团规划设计有限公司|规划设计集团"
    items = parse_surface_lines(text)
    assert len(items) == 1
    assert items[0]["canonical"] == "中国能源建设集团规划设计有限公司"
    assert items[0]["surface"] == "规划设计集团"


def test_parse_surface_lines_skips_same_name():
    text = "surface|华信集团|华信集团"
    assert parse_surface_lines(text) == []


def test_parse_leak_lines():
    text = "leak|entity_leak|规划设计集团|简称残留"
    items = parse_leak_lines(text)
    assert len(items) == 1
    assert items[0]["category"] == "entity_leak"
    assert items[0]["snippet"] == "规划设计集团"


def test_parse_risk_lines_verbatim():
    text = "risk|project_id|251231内控审计|项目编号可定位"
    items = parse_risk_lines(text)
    assert len(items) == 1
    assert items[0]["category"] == "project_id"
    assert items[0]["original"] == "251231内控审计"


def test_parse_risk_lines_with_rewrite():
    text = "risk|table_row|中国北京市子公司投资|某地区子公司投资|地域指纹"
    items = parse_risk_lines(text)
    assert len(items) == 1
    assert items[0]["category"] == "table_row"
    assert items[0]["original"] == "中国北京市子公司投资"
    assert items[0]["rewrite"] == "某地区子公司投资"


def test_parse_risk_lines_legacy_category_maps():
    text = "risk|listing_fingerprint|600182.SH|-"
    items = parse_risk_lines(text)
    assert len(items) == 1
    assert items[0]["category"] == "listing_code"


def test_parse_risk_lines_rejects_bad_category():
    assert parse_risk_lines("risk|unknown|foo|bar") == []


def test_parse_suggest_line():
    assert parse_suggest_line("suggest|客户类别：上市公司") == "客户类别：上市公司"


def test_parse_suggest_line_none():
    assert parse_suggest_line("无") is None


def test_parse_readiness_lines():
    text = "ready|true\nblocker|主体名残留\nnote|金额保留"
    r = parse_readiness_lines(text)
    assert r["ready"] is True
    assert r["blockers"] == ["主体名残留"]
    assert r["notes"] == ["金额保留"]


def test_flow_items_from_chunks():
    units = flow_items_from_text_chunks(["aaa", "bbb"])
    assert len(units) == 2
    assert isinstance(units[0], FlowItem)
    assert units[0].text == "aaa"


def test_scrub_docprops_clears_creator(tmp_path):
    from app.deid.engine.metadata import scrub_docprops, scan_metadata_residuals

    work = tmp_path / "work"
    props = work / "docProps"
    props.mkdir(parents=True)
    core = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:creator>张晓平</dc:creator>
  <cp:lastModifiedBy>1667226511@qq.com</cp:lastModifiedBy>
</cp:coreProperties>"""
    (props / "core.xml").write_text(core, encoding="utf-8")
    cleared = scrub_docprops(work, label="脱敏工具")
    assert any("creator" in c for c in cleared)
    residuals = scan_metadata_residuals(work)
    assert not any("@" in r.get("value", "") for r in residuals)
