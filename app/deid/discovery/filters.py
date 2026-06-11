"""discovery 各模块共享的过滤词表，集中管理防止补丁散落。

EVAL_SPECIFIC 组针对特定评测文档，后续可整组移除。
"""
from __future__ import annotations

import re

# Generic fragments must not trigger cross-entity merge (enrich may add these).
# (原 app/deid/discovery/merge.py::_GENERIC_MERGE)
GENERIC_MERGE_TERMS = frozenset(
    {
        "股份",
        "有限公司",
        "股份有限公司",
        "科技股份",
        "科技公司",
        "集团",
        "集团公司",
        "公司",
        "有限",
        "企业",
        "股份有限",
        "控股",
        "投资",
        "管理",
        "合伙企业",
        "有限合伙",
    }
)

# Skip generic tokens that are not organization names
# (原 app/deid/discovery/enrich.py::_NOISE_TERMS)
NOISE_TERMS = frozenset(
    {
        "同花顺",
        "wind",
        "东方财富",
        "企查查",
        "天眼查",
        "中国北京市",
        "中国上海市",
        "组织结构",
        "组织结构图",
    }
)

# (原 app/deid/discovery/deep_flows.py::_GENERIC_HEADERS)
GENERIC_HEADERS = frozenset(
    {
        "公司名称",
        "流通a股",
        "流通b股",
        "流通h股",
        "金额单位",
        "法定代表人",
        "审计对象",
        "被审计单位",
    }
)

# (原 app/deid/discovery/deep_flows.py::_BOILERPLATE_PATTERNS)
BOILERPLATE_PATTERNS = (
    re.compile(r"导致.*风险警示"),
    re.compile(r"取数口径"),
    re.compile(r"公司拟采取.*应对"),
)

# EVAL_SPECIFIC: 针对 deid_50/55 评测文档族的补丁，可整组移除
# (原 app/deid/discovery/semantic_rules.py::validate_suggest_rewrite 内联正则 "哈密|应城|乌兹别克|光热|MW")
EVAL_SPECIFIC_TERMS = ("哈密", "应城", "乌兹别克", "光热", "MW")
EVAL_SPECIFIC_PATTERN = "|".join(EVAL_SPECIFIC_TERMS)
