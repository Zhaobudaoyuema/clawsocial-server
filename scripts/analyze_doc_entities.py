"""Analyze expected deid entities in a Word document."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

SEED_CEEC = [
    "中国能源建设股份有限公司",
    "中国能源建设集团有限公司",
    "中国葛洲坝集团有限公司",
    "中国葛洲坝集团股份有限公司",
    "中国能源建设集团投资有限公司",
    "中国能源建设集团北方建设投资有限公司",
    "中国能源建设集团华东建设投资有限公司",
    "中国能源建设集团南方建设投资有限公司",
    "中国能源建设集团西北建设投资有限公司",
    "中能建西南投资有限公司",
    "中国能源建设集团资产管理有限公司",
    "中国能源建设集团融资租赁有限公司",
    "中能建基金管理有限公司",
    "中国能源建设集团财务有限公司",
    "中国能建集团装备有限公司",
    "中能建国际建设集团有限公司",
    "中国电力工程顾问集团有限公司",
    "电力规划总院有限公司",
]


def extract_text(path: Path) -> str:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from app.deid.convert import convert_to_markdown, ensure_source_markdown

    suffix = path.suffix.lower()
    if suffix == ".md":
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        return convert_to_markdown(path)
    ensure_source_markdown(path, path.parent)
    return (path.parent / "source.md").read_text(encoding="utf-8", errors="replace")


def main() -> None:
    path = Path(sys.argv[1])
    text = extract_text(path)

    org_re = re.compile(
        r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff·（）()A-Za-z0-9]{2,50}"
        r"(?:有限责任公司|股份有限公司|有限公司|集团公司|集团)",
        re.UNICODE,
    )
    orgs = org_re.findall(text)
    freq = Counter(orgs)

    hereafter = re.findall(
        r"(.{2,60}?)[（(]以下简称[「\"']([^」\"']+)[」\"']",
        text,
    )

    seed_hits = [s for s in SEED_CEEC if s in text]

    # Tier: subject + holding structure core
    tier1 = [
        n
        for n in freq
        if n in {
            "中国能源建设股份有限公司",
            "中国能源建设集团有限公司",
            "中国能源建设集团投资有限公司",
            "中国葛洲坝集团股份有限公司",
            "中国葛洲坝集团有限公司",
        }
        or "中国能源建设集团" in n and "投资" in n and "有限公司" in n
    ]

    out = {
        "file": str(path),
        "total_chars": len(text),
        "header_hint": _extract_header(text),
        "unique_company_like": len(freq),
        "tier1_must_have": sorted(set(tier1)),
        "seed_preset_hits": seed_hits,
        "hereafter_rules": [{"full": a, "short": b} for a, b in hereafter[:15]],
        "top_by_frequency": freq.most_common(35),
        "all_unique_companies": sorted(set(orgs)),
    }

    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("_debug_entity_analysis.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _extract_header(text: str) -> dict[str, str]:
    hints: dict[str, str] = {}
    for key, pat in {
        "subject": r"主体客户名称：([^\s]+)",
        "project": r"项目名称：([^\s]+)",
        "period": r"分析期间：([^\s]+)",
    }.items():
        m = re.search(pat, text)
        if m:
            hints[key] = m.group(1).strip()
    return hints


if __name__ == "__main__":
    main()
