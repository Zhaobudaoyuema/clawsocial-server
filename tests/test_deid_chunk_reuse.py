"""Entity scan chunk plan is reused by semantic scan."""
from app.deid.discovery.llm import (
    apply_scan_chunk_plan,
    build_llm_chunks,
    build_scan_chunk_plan,
    chunk_paragraph_ranges,
    chunks_from_paragraph_ranges,
    count_llm_chunks,
)


def test_chunk_plan_matches_build_llm_chunks():
    text = "段落一\n\n" * 500 + "结尾段\n"
    plan = build_scan_chunk_plan(text)
    direct = build_llm_chunks(text)
    replay = apply_scan_chunk_plan(text, plan)
    assert len(replay) == len(direct)
    assert len(replay) == count_llm_chunks(text)


def test_chunk_plan_survives_preview_replacement():
    original = "公司A 项目编号 251231\n" * 40 + "证券 600642.SHA\n" * 40
    preview = original.replace("公司A", "[公司_1]")
    plan = build_scan_chunk_plan(original)
    orig_chunks = apply_scan_chunk_plan(original, plan)
    prev_chunks = apply_scan_chunk_plan(preview, plan)
    assert len(orig_chunks) == len(prev_chunks)


def test_paragraph_ranges_materialize():
    text = "a\n\nb\n\nc\n\nd\n"
    ranges = chunk_paragraph_ranges(text)
    chunks = chunks_from_paragraph_ranges(text, ranges)
    assert chunks == build_llm_chunks(text)
