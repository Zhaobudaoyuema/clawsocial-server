"""One-off eval for deid_50 desensitized docx."""
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

DOC = Path(r"C:\Users\16672\Downloads\deid_50_20260610_desensitized.docx")
ORIG = Path(r"d:\clawsocial-server\uploads\deid\50\original_中国能源建设股份有限公司-项目风险识别报告-2026-01-30.docx")


def extract_text(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
        text = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", "", text)
        for ent, ch in [("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"), ("&quot;", '"')]:
            text = text.replace(ent, ch)
        return text


def main() -> None:
    text = extract_text(DOC)

    targets = [
        "中国能源建设股份有限公司", "中国能建", "中国能源建设集团", "中能建",
        "葛洲坝", "同花顺", "廉家坝", "规划设计集团", "思源电气", "海得控制",
        "九洲", "启发壹号", "武商", "天健", "能源建设", "能建股份", "CEEC",
        "国务院国资委", "601868",
    ]
    leaks = {t: text.count(t) for t in targets if text.count(t)}

    ph_pat = re.compile(r"\[(?:公司|姓名|机构|实体|人员|人物|项目)_\d+\]")
    placeholders = ph_pat.findall(text)

    companies = re.findall(
        r"[\u4e00-\u9fff]{2,40}(?:股份有限公司|有限责任公司|集团有限公司|有限公司)",
        text,
    )
    co = Counter(companies)

    raw_lines = []
    for line in text.splitlines():
        if re.search(r"(?:有限公司|股份有限公司|集团)", line) and not ph_pat.search(line):
            s = line.strip()
            if s and len(s) < 150:
                raw_lines.append(s)

    stocks = sorted(set(re.findall(r"\d{6}\.[SH]{1,2}[A]?", text)))
    provinces = sorted(set(re.findall(r"中国[\u4e00-\u9fff]{1,8}省", text)))
    project_ids = re.findall(r"251231[^\s\n]{0,40}", text)

    with zipfile.ZipFile(DOC) as z:
        core = z.read("docProps/core.xml").decode("utf-8")
        creator = re.search(r"<dc:creator>(.*?)</dc:creator>", core)
        title = re.search(r"<dc:title>(.*?)</dc:title>", core)

    # Business fingerprint: subsidiary count, revenue scale
    revenue_lines = [l.strip() for l in text.splitlines() if re.search(r"^\d{1,3}(?:,\d{3})+\.\d{2}$", l.strip())]

    report = {
        "file": str(DOC),
        "text_length": len(text),
        "placeholder_count": len(placeholders),
        "placeholder_unique": len(set(placeholders)),
        "company_placeholder_max": max(
            (int(m.group(1)) for m in re.finditer(r"\[公司_(\d+)\]", text)), default=0
        ),
        "person_placeholder_count": len(re.findall(r"\[姓名_\d+\]", text)),
        "target_leaks": leaks,
        "remaining_companies": co.most_common(20),
        "unreplaced_company_lines": raw_lines[:20],
        "stock_codes": stocks,
        "provinces": provinces,
        "project_ids": project_ids,
        "metadata": {
            "creator": creator.group(1) if creator else None,
            "title": title.group(1) if title else None,
        },
        "pii": {
            "phones": re.findall(r"1[3-9]\d{9}", text)[:10],
            "emails": re.findall(r"[\w.-]+@[\w.-]+\.\w+", text)[:10],
            "id_cards": re.findall(r"\d{17}[\dXx]", text)[:10],
        },
        "header_lines": [l.strip() for l in text.splitlines() if l.strip()][:8],
        "risk_notes": [],
    }

    if leaks.get("中国能源建设股份有限公司") or leaks.get("中国能建") or leaks.get("中能建"):
        report["risk_notes"].append("主体公司名称残留")
    if leaks.get("同花顺"):
        report["risk_notes"].append("数据来源'同花顺'未脱敏，可关联到金融风控报告来源")
    if "251231" in text:
        report["risk_notes"].append("项目编号251231保留，可能与内部项目编码体系关联")
    if report["metadata"].get("creator"):
        report["risk_notes"].append(f"文档元数据 creator={report['metadata']['creator']}")
    if report["company_placeholder_max"] >= 90:
        report["risk_notes"].append(f"子公司/关联方数量约{report['company_placeholder_max']}家，大型央企集团特征明显")
    if stocks:
        report["risk_notes"].append(f"保留{len(stocks)}个上市公司股票代码，可反查关联公司")

    # Compare original subject name if exists
    if ORIG.exists():
        orig_text = extract_text(ORIG)
        report["original_subject_hits"] = {
            t: orig_text.count(t)
            for t in ["中国能源建设", "中国能建", "中能建", "601868"]
            if orig_text.count(t)
        }
        report["subject_removed"] = not any(
            text.count(t) for t in ["中国能源建设股份有限公司", "中国能建", "中能建", "601868"]
        )

    out = Path(__file__).resolve().parent.parent / "_debug_deid50_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
