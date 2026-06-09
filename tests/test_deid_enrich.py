"""Tests for discovery enrichment."""
from app.deid.discovery.enrich import enrich_discovered_entities
from app.deid.discovery.rules import DiscoveredEntity


def test_propagate_hereafter_alias():
    sample = "中国能源建设股份有限公司（以下简称「中国能建」）与中能建哈密项目有关。"
    entities = [
        DiscoveredEntity(
            canonical_name="中国能源建设股份有限公司",
            entity_type="company",
            source="llm",
            aliases=["中国能源建设股份有限公司"],
            hit_count=1,
        )
    ]
    enrich_discovered_entities(sample, entities)
    aliases = set(entities[0].aliases)
    assert "中国能建" in aliases


def test_propagate_bond_abbreviation():
    sample = "债券 25中能建MTN001 由中国能源建设股份有限公司发行。"
    entities = [
        DiscoveredEntity(
            canonical_name="中国能源建设股份有限公司",
            entity_type="company",
            source="llm",
            aliases=["中国能源建设股份有限公司", "中国能建"],
            hit_count=2,
        )
    ]
    enrich_discovered_entities(sample, entities)
    assert "中能建" in entities[0].aliases


def test_skips_data_source_noise():
    sample = "当前数据来源：同花顺"
    entities = [
        DiscoveredEntity(
            canonical_name="同花顺",
            entity_type="company",
            source="llm",
            aliases=["同花顺"],
            hit_count=1,
        )
    ]
    enrich_discovered_entities(sample, entities)
    assert entities == []
