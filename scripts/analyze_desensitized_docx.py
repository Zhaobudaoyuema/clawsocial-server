"""Analyze a desensitized DOCX for data leakage risks."""
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path


def extract_text(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
        text = re.sub(r"<w:tab[^>]*/>", "\t", xml)
        text = re.sub(r"</w:p>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        for ent, ch in [("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"), ("&quot;", '"')]:
            text = text.replace(ent, ch)
        return text


def analyze(path: Path) -> dict:
    text = extract_text(path)

    company_tokens = re.findall(r"\[公司_\d+\]", text)
    person_tokens = re.findall(r"\[(?:人物|姓名)_\d+\]", text)
    project_tokens = re.findall(r"\[项目_\d+\]", text)

    phones = re.findall(r"1[3-9]\d{9}", text)
    emails = re.findall(r"[\w.-]+@[\w.-]+\.\w+", text)
    id_cards = re.findall(r"\d{17}[\dXx]", text)

    real_companies = re.findall(
        r"[\u4e00-\u9fff]{2,30}(?:股份有限公司|有限责任公司|集团有限公司|有限公司|集团公司)",
        text,
    )

    titles = ["董事长", "总经理", "董事", "监事", "秘书", "委员", "总裁", "副总"]
    person_candidates = []
    for title in titles:
        for m in re.finditer(r"([\u4e00-\u9fff]{2,4})" + title, text):
            person_candidates.append(m.group(1))

    provinces = re.findall(r"中国[\u4e00-\u9fff]{1,6}省", text)
    amounts = re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", text)
    stocks = re.findall(r"\d{6}\.[SH]{1,2}[A]?", text)
    project_ids = re.findall(r"251231[^\s\n]{0,30}", text)

    keywords = [
        "内控审计",
        "廉家坝",
        "规划设计集团",
        "同花顺",
        "A+H股",
        "葛洲坝",
        "中能建",
        "九洲",
        "思源电气",
        "海得控制",
        "拖欠",
        "抵押",
        "质押",
        "实际控制人",
    ]

    with zipfile.ZipFile(path) as z:
        core = z.read("docProps/core.xml").decode("utf-8")
        creator = re.search(r"<dc:creator>(.*?)</dc:creator>", core)
        modified = re.search(r"<cp:lastModifiedBy>(.*?)</cp:lastModifiedBy>", core)
        created = re.search(r"<dcterms:created[^>]*>(.*?)</dcterms:created>", core)

        extras = ""
        for name in z.namelist():
            if any(x in name for x in ["header", "footer", "footnote", "endnote", "comment"]):
                extras += z.read(name).decode("utf-8", errors="replace")

    samples = []
    for pat in keywords:
        idx = text.find(pat)
        if idx >= 0:
            samples.append({"keyword": pat, "context": text[max(0, idx - 80) : idx + 120]})

    # Top company token frequency
    company_freq = Counter(company_tokens).most_common(15)

    return {
        "file": str(path),
        "file_size_kb": round(path.stat().st_size / 1024, 1),
        "text_length": len(text),
        "token_counts": {
            "company": len(company_tokens),
            "unique_company": len(set(company_tokens)),
            "person": len(person_tokens),
            "unique_person": len(set(person_tokens)),
            "project": len(project_tokens),
            "unique_project": len(set(project_tokens)),
        },
        "top_company_tokens": company_freq,
        "pii": {
            "phones": list(set(phones))[:20],
            "emails": list(set(emails))[:20],
            "id_cards": list(set(id_cards))[:20],
        },
        "real_companies_count": len(set(real_companies)),
        "real_companies": sorted(set(real_companies)),
        "person_candidates": sorted(set(person_candidates)),
        "provinces": sorted(set(provinces)),
        "large_amounts_count": len(amounts),
        "stock_codes": sorted(set(stocks)),
        "project_ids": list(set(project_ids)),
        "keyword_hits": {k: text.count(k) for k in keywords if k in text},
        "metadata": {
            "creator": creator.group(1) if creator else None,
            "lastModifiedBy": modified.group(1) if modified else None,
            "created": created.group(1) if created else None,
        },
        "extras_has_company_names": bool(
            re.search(r"[\u4e00-\u9fff]{4,}(?:公司|集团)", extras)
        ),
        "sensitive_samples": samples[:12],
        "header_snippet": text[:500],
    }


if __name__ == "__main__":
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:\Users\16672\Downloads\中国能源建设股份有限公司-项目风险识别报告-2026-01-30_desensitized (1).docx"
    )
    result = analyze(p)
    out = Path(__file__).resolve().parent.parent / "_debug_desensitized_analysis.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
