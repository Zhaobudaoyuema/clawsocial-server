"""Evaluate a desensitized docx for export readiness leaks."""
from __future__ import annotations

import json
import re
import sys
import zipfile
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


def extract_text(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
        text = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", "", text)
        for ent, ch in [("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"), ("&quot;", '"')]:
            text = text.replace(ent, ch)
        return text


def evaluate(docx_path: Path) -> dict:
    text = extract_text(docx_path)
    leaks = {t: text.count(t) for t in TARGETS if text.count(t)}
    pattern_hits = {}
    for pat, cat in HIGH_RISK_PATTERNS:
        found = re.findall(pat, text)
        if found:
            pattern_hits[cat] = pattern_hits.get(cat, []) + found[:5]

    ph = Counter(re.findall(r"\[(?:公司|姓名)_\d+\]", text))
    report = {
        "file": str(docx_path),
        "text_length": len(text),
        "target_leaks": leaks,
        "pattern_hits": pattern_hits,
        "placeholder_count": sum(ph.values()),
        "export_ready": not leaks and not pattern_hits,
    }
    return report


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:\Users\16672\Downloads\deid_55_20260610_desensitized.docx"
    )
    report = evaluate(path)
    out = Path(__file__).resolve().parent.parent / "_debug_eval_export.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
