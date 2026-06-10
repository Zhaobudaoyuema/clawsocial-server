"""Apply deep rewrite pairs to an existing de-identified docx."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from app.deid.engine.plan import MatchSpan, ReplacementPlan
from app.deid.engine.xml import replace as xml_replace
from app.deid.engine.xml.walker import target_xml_files
from app.deid.office_io import pack_docx, unpack_docx


def apply_deep_pairs(input_path: Path, output_path: Path, pairs: list[dict]) -> int:
    """
    Apply literal original→rewritten pairs to docx XML.

    pairs: [{original, rewritten}, ...]
    Returns total replacement count.
    """
    if not pairs:
        shutil.copy2(input_path, output_path)
        return 0

    spans = [
        MatchSpan(
            start=0,
            end=0,
            original=p["original"],
            replacement=p["rewritten"],
            entity_type="deep",
            source="deep",
        )
        for p in pairs
        if p.get("original") and p.get("rewritten") and p["original"] != p["rewritten"]
    ]
    if not spans:
        shutil.copy2(input_path, output_path)
        return 0

    plan = ReplacementPlan(spans=spans)
    plan.finalize()

    work = Path(tempfile.mkdtemp(prefix="deid_deep_"))
    try:
        fast_io = os.getenv("DEID_FAST_IO", "1").strip().lower() not in ("0", "false", "off")
        unpack_docx(input_path, work, merge=False, fast=fast_io)
        total = 0
        for xf in target_xml_files(work):
            _, cnt = xml_replace.process_xml_file(xf, plan)
            total += cnt
        pack_docx(work, output_path, validate=False, fast=fast_io)
        return total
    finally:
        shutil.rmtree(work, ignore_errors=True)
