"""Tests for conclusion rehydrate (mapping restore)."""
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.deid.rehydrate import build_placeholder_map, rehydrate_text
from app.deid.service import (
    archive_expired_job_files,
    archive_job_files,
    purge_expired_mapping_jobs,
)
from app.deid.storage import DEID_ROOT
from app.models_deid import DeidEntityMapping, DeidJob
from app.time_utils import now_beijing
from tests.test_deid import _ensure_fixture, _entity_ids


class _Row:
    def __init__(self, placeholder: str, original_text: str):
        self.placeholder = placeholder
        self.original_text = original_text


def test_build_placeholder_map_prefers_longest_alias():
    rows = [
        _Row("[公司_1]", "能建"),
        _Row("[公司_1]", "中国能源建设股份有限公司"),
    ]
    assert build_placeholder_map(rows)["[公司_1]"] == "中国能源建设股份有限公司"


def test_rehydrate_text_replaces_known_placeholders():
    ph_map = {"[公司_1]": "中国能源建设股份有限公司", "[姓名_1]": "张三"}
    text = "报告认为 [公司_1] 的 [姓名_1] 需关注。"
    result = rehydrate_text(text, ph_map)
    assert "中国能源建设股份有限公司" in result.text
    assert "张三" in result.text
    assert "[公司_1]" not in result.text
    assert set(result.resolved) == {"[公司_1]", "[姓名_1]"}


def test_rehydrate_text_longer_placeholder_first():
    ph_map = {"[公司_10]": "十号公司", "[公司_1]": "一号公司"}
    text = "涉及 [公司_10] 与 [公司_1]"
    result = rehydrate_text(text, ph_map)
    assert "十号公司" in result.text
    assert "一号公司" in result.text


def test_rehydrate_text_unresolved():
    result = rehydrate_text("未知 [公司_99]", {"[公司_1]": "A"})
    assert "[公司_99]" in result.text
    assert result.unresolved == ["[公司_99]"]


def test_rehydrate_text_bare_placeholder_without_brackets():
    ph_map = {"[公司_1]": "中国能源建设股份有限公司"}
    result = rehydrate_text("报告认为公司_1存在风险。", ph_map)
    assert "中国能源建设股份有限公司" in result.text
    assert "公司_1" not in result.text
    assert result.resolved == ["[公司_1]"]


def test_rehydrate_text_mixed_bracket_and_bare():
    ph_map = {"[公司_1]": "甲公司", "[姓名_1]": "张三"}
    text = "结论：[公司_1] 负责人姓名_1 需关注。"
    result = rehydrate_text(text, ph_map)
    assert "甲公司" in result.text
    assert "张三" in result.text
    assert set(result.resolved) == {"[公司_1]", "[姓名_1]"}


def test_rehydrate_text_bare_unresolved():
    result = rehydrate_text("未知公司_99", {"[公司_1]": "A"})
    assert "公司_99" in result.text
    assert result.unresolved == ["公司_99"]


def _run_done_job(client: TestClient) -> int:
    _ensure_fixture()
    fixture = Path(__file__).parent / "fixtures" / "spic_sample.docx"
    with open(fixture, "rb") as f:
        r = client.post(
            "/api/deid/jobs",
            files={
                "file": (
                    "spic_sample.docx",
                    f,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={"use_worker": "false"},
        )
    assert r.status_code == 200
    job_id = r.json()["id"]
    client.post(f"/api/deid/jobs/{job_id}/scan")
    ids = _entity_ids(client, job_id)
    r = client.post(f"/api/deid/jobs/{job_id}/run", json={"entity_ids": ids})
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    return job_id


def test_api_rehydrate_done_job(client: TestClient, db, seeded_db):
    job_id = _run_done_job(client)
    mapping = client.get(f"/api/deid/jobs/{job_id}/mapping").json()
    assert mapping
    ph = mapping[0]["placeholder"]
    r = client.post(
        f"/api/deid/jobs/{job_id}/rehydrate",
        json={"text": f"分析结论：{ph} 存在风险"},
    )
    assert r.status_code == 200
    data = r.json()
    assert ph not in data["text"]
    assert ph in data["resolved"]


def test_api_export_archived_returns_400(client: TestClient, db: Session, seeded_db):
    job_id = _run_done_job(client)
    job = db.get(DeidJob, job_id)
    archive_job_files(db, job)
    db.commit()
    db.expire_all()
    assert db.get(DeidJob, job_id).status == "archived"
    api_job = client.get(f"/api/deid/jobs/{job_id}").json()
    assert api_job["status"] == "archived"

    r = client.get(f"/api/deid/jobs/{job_id}/export?override_ack=true")
    # /api/deid returns plain-text errors with HTTP 200 (see main.py exception handler)
    assert "文件已清理" in r.text


def test_api_rehydrate_archived_job(client: TestClient, db: Session, seeded_db):
    job_id = _run_done_job(client)
    mapping = client.get(f"/api/deid/jobs/{job_id}/mapping").json()
    ph = mapping[0]["placeholder"]
    job = db.get(DeidJob, job_id)
    archive_job_files(db, job)
    db.commit()
    r = client.post(
        f"/api/deid/jobs/{job_id}/rehydrate",
        json={"text": f"结论 {ph}"},
    )
    assert r.status_code == 200
    assert ph not in r.json()["text"]


def test_cleanup_phase1_archives_keeps_mapping(client: TestClient, db: Session, seeded_db):
    job_id = _run_done_job(client)
    job = db.get(DeidJob, job_id)
    job.completed_at = now_beijing() - timedelta(hours=9)
    db.commit()
    (DEID_ROOT / str(job_id)).mkdir(parents=True, exist_ok=True)
    (DEID_ROOT / str(job_id) / "keep.txt").write_text("x", encoding="utf-8")

    archived = archive_expired_job_files(db)
    assert archived == 1

    db.expire_all()
    job = db.get(DeidJob, job_id)
    assert job.status == "archived"
    assert job.files_purged_at is not None
    assert not (DEID_ROOT / str(job_id)).exists()
    assert db.query(DeidEntityMapping).filter(DeidEntityMapping.job_id == job_id).count() > 0


def test_backfill_mappings_for_legacy_done_job(client: TestClient, db: Session, seeded_db):
    """Jobs completed before _write_mappings shipped can be backfilled from job_entities."""
    job_id = _run_done_job(client)
    db.query(DeidEntityMapping).filter(DeidEntityMapping.job_id == job_id).delete()
    db.commit()
    assert db.query(DeidEntityMapping).filter(DeidEntityMapping.job_id == job_id).count() == 0

    listed = client.get("/api/deid/jobs").json()
    row = next(j for j in listed if j["id"] == job_id)
    assert row["rehydrate_available"] is True
    assert db.query(DeidEntityMapping).filter(DeidEntityMapping.job_id == job_id).count() > 0


def test_cleanup_phase2_purges_old_mapping(client: TestClient, db: Session, seeded_db):
    job_id = _run_done_job(client)
    job = db.get(DeidJob, job_id)
    archive_job_files(db, job)
    job.completed_at = now_beijing() - timedelta(days=91)
    db.commit()

    purged = purge_expired_mapping_jobs(db)
    assert purged == 1

    db.expire_all()
    assert db.get(DeidJob, job_id) is None
    assert db.query(DeidEntityMapping).filter(DeidEntityMapping.job_id == job_id).count() == 0
