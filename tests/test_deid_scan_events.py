"""Tests for deid scan live progress (event bus, doc stats, SSE)."""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path

import pytest
from docx import Document

from app.deid.engine.pipeline import extract_doc_sample_and_stats, extract_sample_text
from app.deid.scan_events import ScanEventBus


def test_scan_event_bus_emit_subscribe():
    bus = ScanEventBus()
    received: list[dict] = []

    async def collect():
        async for ev in bus.subscribe(1):
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


def test_extract_doc_sample_and_stats(tmp_path):
    doc_path = tmp_path / "sample.docx"
    doc = Document()
    doc.add_paragraph("审计底稿：国家电投集团下属单位往来。")
    doc.add_paragraph("涉及国家电投与电投产融的关联交易。")
    doc.save(doc_path)

    text, stats = extract_doc_sample_and_stats(doc_path)
    assert "国家电投" in text
    assert stats["paragraph_count"] >= 2
    assert stats["char_count"] > 10
    assert extract_sample_text(doc_path) == text


def test_extract_doc_stats_strict_ooxml(tmp_path):
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://purl.oclc.org/ooxml/wordprocessingml/main">'
        "<w:body><w:p><w:r><w:t>中国能源建设股份有限公司审计报告</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    doc_path = tmp_path / "strict.docx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", doc_xml)
    doc_path.write_bytes(buf.getvalue())

    text, stats = extract_doc_sample_and_stats(doc_path)
    assert "中国能源建设股份有限公司" in text
    assert stats["paragraph_count"] == 1
    assert stats["char_count"] >= 10


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
