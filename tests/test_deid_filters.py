"""filters.py 收敛后各常量组可导入且内容非空。"""
from app.deid.discovery import filters


def test_filter_groups_exist():
    assert "有限公司" in filters.GENERIC_MERGE_TERMS
    assert filters.NOISE_TERMS
    assert filters.GENERIC_HEADERS
    assert filters.BOILERPLATE_PATTERNS
    assert filters.EVAL_SPECIFIC_TERMS


def test_old_modules_reference_filters():
    from app.deid.discovery import merge, enrich, deep_flows
    assert merge._GENERIC_MERGE is filters.GENERIC_MERGE_TERMS
    assert enrich._NOISE_TERMS is filters.NOISE_TERMS
    assert deep_flows._GENERIC_HEADERS is filters.GENERIC_HEADERS
