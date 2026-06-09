"""Tests for document discovery rules."""
from app.deid.discovery.rules import discover_doc_rules, discover_hereafter_rules, discover_org_suffix_rules
from app.deid.engine.plan import normalize_for_match


def test_hereafter_rule():
    sample = "中国能源建设集团有限公司（以下简称「中国能建」）下属单位。"
    text_norm = normalize_for_match(sample)
    found = discover_hereafter_rules(sample, text_norm)
    assert len(found) >= 1
    assert any("中国能建" in e.aliases for e in found)
    assert found[0].source == "rule"


def test_org_suffix_rule():
    sample = "审计对象包括中能建氢能源有限公司及其关联方。"
    text_norm = normalize_for_match(sample)
    found = discover_org_suffix_rules(sample, text_norm)
    names = [e.canonical_name for e in found]
    assert any("中能建氢能源有限公司" in n for n in names)


def test_discover_doc_rules_combined():
    sample = (
        "中国能源建设集团有限公司（以下简称「中国能建」）"
        "与中能建氢能源有限公司存在关联交易。"
    )
    found = discover_doc_rules(sample)
    assert len(found) >= 2
