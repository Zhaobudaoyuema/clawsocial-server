"""Tests for entity rescan pipeline — initial / re-run / global experience."""
import pytest

from app.deid.discovery.entity_rescan import (
    diff_canonical_new_in_round,
    diff_canonical_vs_initial,
    snapshot_entities,
)
from app.deid.discovery.experience_store import (
    append_global_experience,
    build_experience_prompt_block,
    list_global_experience_texts,
)
from app.deid.discovery.flow_parse import parse_exp_lines
from app.deid.discovery.merge import MergedEntity


def test_parse_exp_lines_single():
    text = "exp|表头简称需在初次识别时补全\n无"
    items = parse_exp_lines(text)
    assert items == ["表头简称需在初次识别时补全"]


def test_global_experience_fifo(db, seeded_db):
    for i in range(21):
        append_global_experience(db, f"经验{i:02d}", source_job_id=None)
    db.commit()
    lines = list_global_experience_texts(db, limit=20)
    assert len(lines) == 20
    assert lines[0] == "经验01"
    assert lines[-1] == "经验20"


def test_build_experience_prompt_block_inject():
    block = build_experience_prompt_block(["a", "b"])
    assert "--- 历史经验" in block
    assert "- a" in block


def test_diff_canonical_vs_initial():
    initial = [{"canonical_name": "A公司", "entity_type": "company", "aliases": []}]
    current = [
        MergedEntity(canonical_name="A公司", entity_type="company", source="llm", aliases=["A公司"]),
        MergedEntity(canonical_name="B公司", entity_type="company", source="llm", aliases=["B公司"]),
    ]
    added = diff_canonical_vs_initial(initial, current)
    assert added == ["B公司"]


def test_diff_canonical_new_in_round_llm_only():
    before = [
        MergedEntity(canonical_name="A", entity_type="company", source="remembered", aliases=["A"]),
    ]
    after = [
        MergedEntity(canonical_name="A", entity_type="company", source="remembered", aliases=["A"]),
        MergedEntity(canonical_name="B", entity_type="company", source="llm", aliases=["B"]),
        MergedEntity(canonical_name="C", entity_type="company", source="manual", aliases=["C"]),
    ]
    new_llm = diff_canonical_new_in_round(before, after)
    assert new_llm == ["B"]


def test_snapshot_entities():
    ents = [
        MergedEntity(canonical_name="X", entity_type="company", source="llm", aliases=["X", "x"]),
    ]
    snap = snapshot_entities(ents)
    assert snap[0]["canonical_name"] == "X"
    assert "x" in snap[0]["aliases"]


@pytest.mark.asyncio
async def test_re_run_scan_offline(db, seeded_db):
    from app.deid.service import re_run_scan_job
    from app.models_deid import DeidJob

    job = DeidJob(
        status="scanned",
        pack_ids_json="[]",
        original_filename="t.docx",
        stored_path="deid/1/source.md",
        use_worker=True,
        initial_entities_snapshot_json='[{"canonical_name":"A","entity_type":"company","aliases":[]}]',
    )
    db.add(job)
    db.commit()

    with pytest.raises(Exception) as exc:
        await re_run_scan_job(db, job.id, worker_router=None)
    assert exc.value.status_code == 503
