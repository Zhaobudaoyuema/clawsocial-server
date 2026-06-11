"""Tests for markdown de-identification pipeline."""
from pathlib import Path

from app.deid.convert import convert_to_markdown, ensure_source_markdown
from app.deid.engine.markdown_pipeline import (
    extract_md_sample_and_stats,
    extract_sample_text,
    partition_semantic_pairs_text,
    residual_scan_md,
    run_markdown_pipeline,
)


def test_extract_md_sample_and_stats(tmp_path):
    md_path = tmp_path / "source.md"
    md_path.write_text(
        "# 标题\n\n国家电投集团审计底稿\n\n| 列1 | 列2 |\n| --- | --- |\n| a | b |\n",
        encoding="utf-8",
    )
    text, stats = extract_md_sample_and_stats(md_path)
    assert "国家电投" in text
    assert stats["paragraph_count"] >= 2
    assert stats["char_count"] > 10
    assert stats["table_count"] == 1
    assert extract_sample_text(md_path) == text


def test_residual_scan_md(tmp_path):
    md_path = tmp_path / "out.md"
    md_path.write_text("已替换 [公司_1] 内容", encoding="utf-8")
    entities = [
        {
            "canonical_name": "国家电投",
            "aliases": ["国家电投"],
            "is_excluded": False,
        }
    ]
    result = residual_scan_md(md_path, entities)
    assert result["passed"] is True
    assert result["metadata_clean"] is True


def test_partition_semantic_pairs_text():
    text = "项目名称：251231内控审计\n无关段落"
    applicable, missed = partition_semantic_pairs_text(
        text,
        [
            {"original": "251231内控审计", "rewritten": "内控审计项目"},
            {"original": "缺失", "rewritten": "x"},
        ],
    )
    assert len(applicable) == 1
    assert len(missed) == 1


def test_run_markdown_pipeline_entity_and_semantic(tmp_path):
    src = tmp_path / "source.md"
    src.write_text("中国能建251231内控审计\n", encoding="utf-8")
    out = tmp_path / "out.md"
    entities = [
        {
            "canonical_name": "中国能建",
            "entity_type": "company",
            "placeholder": "[公司_1]",
            "source": "manual",
            "is_excluded": False,
            "aliases": ["中国能建"],
        },
    ]
    pairs = [
        {
            "original": "251231内控审计",
            "rewritten": "内控审计项目",
            "category": "project_id",
        },
    ]
    result = run_markdown_pipeline(src, out, entities, [], [], semantic_pairs=pairs)
    assert result["engine"] == "markdown"
    assert result["semantic_applied_count"] == 1
    text = out.read_text(encoding="utf-8")
    assert "[公司_1]" in text
    assert "内控审计项目" in text
    assert "251231" not in text


def test_convert_docx_to_markdown(tmp_path):
    from docx import Document

    doc_path = tmp_path / "sample.docx"
    doc = Document()
    long_text = "国家电投集团审计底稿。" * 10
    doc.add_paragraph(long_text)
    doc.save(doc_path)

    text = convert_to_markdown(doc_path)
    assert "国家电投" in text

    md_path = ensure_source_markdown(doc_path, tmp_path)
    assert md_path.name == "source.md"
    assert "国家电投" in md_path.read_text(encoding="utf-8")
