"""Tests for deid scan live progress (event bus, doc stats, SSE)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from docx import Document

from app.deid.engine.markdown_pipeline import extract_md_sample_and_stats, extract_sample_text
from app.deid.scan_events import ScanEventBus


def test_scan_event_bus_emit_subscribe():
    bus = ScanEventBus()
    received: list[dict] = []

    async def collect():
        async for ev, _is_replay in bus.subscribe(1):
            received.append(ev)
            if ev.get("type") == "done":
                break

    bus.emit(1, {"type": "phase", "phase": "extract", "message": "x", "percent": 5})
    bus.emit(1, {"type": "done", "entity_count": 3})
    bus.close(1)

    asyncio.run(collect())
    assert len(received) == 2
    assert received[0]["type"] == "phase"
    assert received[1]["entity_count"] == 3


def test_extract_md_sample_and_stats(tmp_path):
    md_path = tmp_path / "source.md"
    md_path.write_text(
        "审计底稿：国家电投集团下属单位往来。\n涉及国家电投与电投产融的关联交易。\n",
        encoding="utf-8",
    )

    text, stats = extract_md_sample_and_stats(md_path)
    assert "国家电投" in text
    assert stats["paragraph_count"] >= 2
    assert stats["char_count"] > 10
    assert extract_sample_text(md_path) == text


def test_scan_stream_sse(client, db, seeded_db):
    fixture = Path(__file__).parent / "fixtures" / "spic_sample.docx"
    if not fixture.exists():
        doc = Document()
        doc.add_paragraph("国家电投集团审计底稿")
        fixture.parent.mkdir(parents=True, exist_ok=True)
        doc.save(fixture)

    with open(fixture, "rb") as f:
        r = client.post(
            "/api/deid/jobs",
            files={"file": ("spic_sample.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    job_id = r.json()["id"]

    from app.deid.scan_events import get_scan_event_bus

    bus = get_scan_event_bus()
    bus.emit(job_id, {"type": "phase", "phase": "extract", "percent": 10, "message": "test"})
    bus.emit(job_id, {"type": "done", "entity_count": 1, "scan_summary": {}})

    with client.stream("GET", f"/api/deid/jobs/{job_id}/scan-stream") as resp:
        assert resp.status_code == 200
        lines = []
        for line in resp.iter_lines():
            if line.startswith("data:"):
                lines.append(json.loads(line[5:].strip()))
            if lines and lines[-1].get("type") == "done":
                break
    assert any(ev.get("type") == "phase" for ev in lines)
    assert any(ev.get("type") == "done" for ev in lines)


def test_subscribe_skip_replay():
    bus = ScanEventBus()
    bus.emit(1, {"type": "phase", "message": "初次识别完成", "percent": 100})
    bus.emit(1, {"type": "done", "entity_count": 1})
    received: list[dict] = []

    async def collect():
        async for ev, _is_replay in bus.subscribe(1, replay=False):
            received.append(ev)
            break

    async def main():
        task = asyncio.create_task(collect())
        await asyncio.sleep(0)
        bus.emit(1, {"type": "rescan_start", "re_run_count": 1})
        bus.close(1)
        await task

    asyncio.run(main())
    assert len(received) == 1
    assert received[0]["type"] == "rescan_start"
