"""Tests for Worker call audit log."""
from app.deid.worker_call_store import (
    delete_worker_calls_for_job,
    list_worker_calls,
    record_worker_call,
)
from app.models_deid import DeidJob, DeidWorkerCall


def _make_job(db, job_id: int = 1) -> DeidJob:
    job = DeidJob(
        id=job_id,
        status="scanned",
        original_filename="t.docx",
        stored_path="deid/1/original_t.docx",
        pack_ids_json="[]",
    )
    db.add(job)
    db.commit()
    return job


def test_record_and_list_worker_calls(db):
    _make_job(db)
    record_worker_call(
        db,
        job_id=1,
        flow_id="deep_detect",
        request_id="deep_detect-1-0-abc",
        chunk_index=1,
        chunk_total=3,
        model="test-model",
        system_prompt="sys",
        user_message="user chunk",
        response="risk|data_source|同花顺|-",
        prompt_tokens=100,
        completion_tokens=20,
        parsed_count=1,
        elapsed_ms=500,
    )
    out = list_worker_calls(db, 1)
    assert len(out) == 1
    assert out[0]["flow_id"] == "deep_detect"
    assert out[0]["user_message"] == "user chunk"
    assert "同花顺" in (out[0]["response"] or "")


def test_delete_worker_calls_with_job(db):
    _make_job(db, 2)
    record_worker_call(
        db,
        job_id=2,
        flow_id="entity_scan",
        request_id="entity_scan-2-0",
        chunk_index=1,
        chunk_total=1,
        model="m",
        system_prompt="s",
        user_message="u",
        response="ok",
    )
    delete_worker_calls_for_job(db, 2)
    db.commit()
    assert db.query(DeidWorkerCall).filter(DeidWorkerCall.job_id == 2).count() == 0
