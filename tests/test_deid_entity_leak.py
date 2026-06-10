"""Tests for entity leak scan during initial discovery."""
from app.deid.discovery.entity_leak import leaks_to_entities
from app.deid.discovery.merge import MergedEntity, merge_entities


def test_leaks_to_entities_finds_org_name():
    sample = "因规划设计集团下属企业工程款的情况，目前处理中"
    leaks = [
        {"category": "entity_leak", "snippet": "规划设计集团", "note": "简称"},
    ]
    found = leaks_to_entities(leaks, sample)
    assert len(found) == 1
    assert found[0].canonical_name == "规划设计集团"
    assert found[0].source == "leak_verify"


def test_leaks_to_entities_skips_stock_code():
    sample = "持有600642.SHA股"
    leaks = [{"category": "entity_leak", "snippet": "600642.SHA", "note": "代码"}]
    assert leaks_to_entities(leaks, sample) == []


def test_leaks_merge_into_base():
    base = [
        MergedEntity(
            canonical_name="中国能建",
            entity_type="company",
            source="llm",
            aliases=["中国能建"],
        )
    ]
    sample = "规划设计集团下属企业"
    leaks = [{"category": "entity_leak", "snippet": "规划设计集团", "note": ""}]
    discovered = leaks_to_entities(leaks, sample)
    merged = merge_entities(base + discovered)
    names = {e.canonical_name for e in merged}
    assert "规划设计集团" in names
    assert "中国能建" in names
