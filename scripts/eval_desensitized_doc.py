"""Evaluate a desensitized markdown document."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deid.engine.markdown_pipeline import (
    CREDIT_CODE_RE,
    ID_CARD_RE,
    PHONE_RE,
    extract_md_sample_and_stats,
)

DOC = Path("desensitized.md")


def main() -> None:
    text, stats = extract_md_sample_and_stats(DOC)

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

    report = {
        "file": str(DOC),
        "stats": stats,
        "placeholder_count": len(placeholders),
        "placeholder_top": Counter(placeholders).most_common(15),
        "target_leaks": leaks,
        "company_like_top": Counter(companies).most_common(20),
        "credit_codes": len(CREDIT_CODE_RE.findall(text)),
        "id_cards": len(ID_CARD_RE.findall(text)),
        "phones": len(PHONE_RE.findall(text)),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
