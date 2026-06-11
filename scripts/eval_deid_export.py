"""Evaluate a desensitized markdown export for readiness leaks."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

TARGETS = [
    "中国能源建设股份有限公司",
    "中国能建",
    "中国能源建设集团",
    "中能建",
    "葛洲坝",
    "同花顺",
    "廉家坝",
    "规划设计集团",
    "思源电气",
    "海得控制",
    "九洲",
    "能源建设",
    "601868",
]

HIGH_RISK_PATTERNS = [
    (r"规划设计集团", "entity_name"),
    (r"251231[^\s\n]{0,30}内控", "project_id"),
    (r"\d{6}\.[A-Z]{2,4}", "listing_code"),
    (r"哈密.{0,20}光", "project_name"),
    (r"应城.{0,20}MW", "project_name"),
    (r"乌兹别克", "project_name"),
]


def extract_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def evaluate(md_path: Path) -> dict:
    text = extract_text(md_path)
    leaks = {t: text.count(t) for t in TARGETS if text.count(t)}
    pattern_hits = {}
    for pat, label in HIGH_RISK_PATTERNS:
        hits = re.findall(pat, text)
        if hits:
            pattern_hits[label] = hits[:10]
    ph = re.findall(r"\[(?:公司|姓名|机构|实体|人员)_\d+\]", text)
    return {
        "file": str(md_path),
        "char_count": len(text),
        "placeholder_count": len(ph),
        "placeholder_top": Counter(ph).most_common(10),
        "target_leaks": leaks,
        "pattern_hits": pattern_hits,
    }


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("desensitized.md")
    report = evaluate(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
