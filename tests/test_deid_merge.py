"""Tests for entity merge deduplication."""
from app.deid.discovery.merge import MergedEntity, merge_entities


def test_merge_same_entity_different_sources():
    llm = MergedEntity(
        canonical_name="中国能源建设股份有限公司",
        entity_type="company",
        source="llm",
        aliases=["中国能源建设股份有限公司", "中国能建"],
        hit_count=5,
    )
    remembered = MergedEntity(
        canonical_name="中国能建",
        entity_type="company",
        source="remembered",
        aliases=["中国能建", "中能建"],
        hit_count=10,
        library_entity_id=1,
    )
    out = merge_entities([llm, remembered])
    assert len(out) == 1
    assert out[0].canonical_name == "中国能源建设股份有限公司"
    assert out[0].library_entity_id == 1


def test_merge_does_not_collapse_unrelated_companies_with_shared_generic_alias():
    a = MergedEntity(
        canonical_name="思源电气股份有限公司",
        entity_type="company",
        source="llm",
        aliases=["思源电气股份有限公司", "科技股份"],
        hit_count=3,
    )
    b = MergedEntity(
        canonical_name="上海海得控制系统股份有限公司",
        entity_type="company",
        source="llm",
        aliases=["上海海得控制系统股份有限公司", "科技股份"],
        hit_count=2,
    )
    c = MergedEntity(
        canonical_name="哈尔滨九洲集团股份有限公司",
        entity_type="company",
        source="llm",
        aliases=["哈尔滨九洲集团股份有限公司"],
        hit_count=1,
    )
    out = merge_entities([a, b, c])
    assert len(out) == 3
    names = {e.canonical_name for e in out}
    assert "思源电气股份有限公司" in names
    assert "上海海得控制系统股份有限公司" in names
    assert "哈尔滨九洲集团股份有限公司" in names


def test_merge_keeps_stock_codes_separate():
    a = MergedEntity(
        canonical_name="244323.SH",
        entity_type="company",
        source="llm",
        aliases=["244323.SH"],
        hit_count=1,
    )
    b = MergedEntity(
        canonical_name="242473.SH",
        entity_type="company",
        source="llm",
        aliases=["242473.SH"],
        hit_count=1,
    )
    out = merge_entities([a, b])
    assert len(out) == 2
