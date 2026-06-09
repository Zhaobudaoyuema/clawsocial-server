"""Evaluate desensitized docx output."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deid.engine.pipeline import (
    CREDIT_CODE_RE,
    ID_CARD_RE,
    PHONE_RE,
    extract_doc_sample_and_stats,
)

DOC = Path(r"C:\Users\16672\Downloads\中国能源建设股份有限公司-项目风险识别报告-2026-01-30_desensitized.docx")


def main() -> None:
    text, stats = extract_doc_sample_and_stats(DOC)

    ph_pat = re.compile(r"\[(?:公司|姓名|机构|实体|人员)_\d+\]")
    placeholders = ph_pat.findall(text)

    targets = [
        "中国能源建设股份有限公司",
        "中国能建",
        "中国能源建设集团",
        "中能建",
        "天健会计师事务所",
        "同花顺",
    ]
    leaks = {t: text.count(t) for t in targets if text.count(t)}

    companies = re.findall(
        r"[\u4e00-\u9fff]{2,40}(?:股份有限公司|有限责任公司|集团有限公司|有限公司)",
        text,
    )
    co = Counter(companies)

    # subsidiaries not replaced (no bracket placeholder nearby)
    raw_lines_with_company = []
    for line in text.splitlines():
        if re.search(r"(?:有限公司|股份有限公司|集团)", line) and not ph_pat.search(line):
            s = line.strip()
            if s and len(s) < 120:
                raw_lines_with_company.append(s)

    report = {
        "file": str(DOC),
        "stats": stats,
        "placeholder_count": len(placeholders),
        "placeholder_unique": len(set(placeholders)),
        "placeholder_samples": sorted(set(placeholders))[:15],
        "placeholder_max_num": max(
            (int(m.group(1)) for m in re.finditer(r"\[公司_(\d+)\]", text)),
            default=0,
        ),
        "target_leaks": leaks,
        "remaining_company_names": co.most_common(30),
        "unreplaced_company_lines": raw_lines_with_company[:25],
        "credit_codes": CREDIT_CODE_RE.findall(text),
        "id_cards": ID_CARD_RE.findall(text),
        "phones": PHONE_RE.findall(text),
        "head": text[:1800],
        "notable_gaps": [],
        "leak_contexts": {},
    }

    for kw in [
        "中能建",
        "同花顺",
        "启发壹号",
        "武商",
        "九洲",
        "天健",
        "中国能源",
    ]:
        idx = 0
        hits: list[str] = []
        while True:
            i = text.find(kw, idx)
            if i < 0:
                break
            hits.append(text[max(0, i - 50) : i + len(kw) + 50].replace("\n", " "))
            idx = i + 1
            if len(hits) >= 3:
                break
        if hits:
            report["leak_contexts"][kw] = hits

    ph_types = Counter(re.findall(r"\[(公司|姓名|机构|实体|人员)_\d+\]", text))
    report["placeholder_by_type"] = dict(ph_types)
    report["person_placeholder_count"] = len(re.findall(r"\[姓名_\d+\]", text))

    if leaks:
        report["notable_gaps"].append(f"主体名称残留: {leaks}")
    if co:
        report["notable_gaps"].append(f"仍有 {len(co)} 种公司全称/简称未替换")
    if any("天健" in n for n in companies):
        report["notable_gaps"].append("白名单审计所可能未保留或误替换需核对")

    out = ROOT / "logs" / "desensitized_eval.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
