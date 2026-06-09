"""Tests for document discovery rules."""
from app.deid.discovery.rules import discover_hereafter_rules
from app.deid.engine.plan import normalize_for_match


def test_hereafter_rule():
    sample = "中国能源建设集团有限公司（以下简称「中国能建」）下属单位。"
    text_norm = normalize_for_match(sample)
    found = discover_hereafter_rules(sample, text_norm)
    assert len(found) >= 1
    assert any("中国能建" in e.aliases for e in found)
    assert found[0].source == "rule"
