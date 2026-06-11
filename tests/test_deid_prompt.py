"""Tests for scan prompt settings API."""
from app.deid.prompts import DEFAULT_SCAN_PROMPT, build_scan_system_prompt


def test_default_scan_prompt_uses_line_format():
    assert "type|规范全称" in DEFAULT_SCAN_PROMPT or "type|名称" in DEFAULT_SCAN_PROMPT
    assert "scan_v4" in DEFAULT_SCAN_PROMPT
    assert "禁止用逗号" in DEFAULT_SCAN_PROMPT
    assert "JSON" not in DEFAULT_SCAN_PROMPT or "不要 JSON" in DEFAULT_SCAN_PROMPT
    result = build_scan_system_prompt("GLOBAL # scan_v2", "EXTRA RULES")
    assert "EXTRA RULES" in result
    assert "本任务补充" in result
    assert "scan_v4" in result


def test_get_scan_prompt_settings(client):
    r = client.get("/api/deid/settings/scan-prompt")
    assert r.status_code == 200
    data = r.json()
    assert "prompt" in data
    assert data["default_prompt"] == DEFAULT_SCAN_PROMPT


def test_update_and_reset_scan_prompt(client):
    r = client.put("/api/deid/settings/scan-prompt", json={"prompt": "CUSTOM PROMPT XYZ"})
    assert r.status_code == 200
    assert r.json()["prompt"] == "CUSTOM PROMPT XYZ"

    r = client.post("/api/deid/settings/scan-prompt/reset")
    assert r.status_code == 200
    assert r.json()["prompt"] == DEFAULT_SCAN_PROMPT


def test_effective_prompt_with_job_extra(client, db, seeded_db):
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "spic_sample.docx"
    if not fixture.exists():
        from docx import Document

        doc = Document()
        doc.add_paragraph("test")
        fixture.parent.mkdir(parents=True, exist_ok=True)
        doc.save(fixture)

    with open(fixture, "rb") as f:
        r = client.post(
            "/api/deid/jobs",
            data={"prompt_extra": "ONLY FOR THIS JOB"},
            files={"file": ("t.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    assert r.status_code == 200
    job_id = r.json()["id"]
    r = client.get(f"/api/deid/jobs/{job_id}/effective-prompt")
    assert r.status_code == 200
    data = r.json()
    assert "ONLY FOR THIS JOB" in data["effective_prompt"]
