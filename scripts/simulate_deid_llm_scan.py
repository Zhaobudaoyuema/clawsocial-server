"""Simulate one LLM scan chunk against live Worker (no UI)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deid.discovery.llm import _chunk_text, discover_llm
from app.deid.discovery.llm_parse import parse_llm_entities
from app.deid.engine.pipeline import extract_sample_text
from app.deid.prompts import build_default_scan_prompt, build_scan_user_message
from app.deid.worker.relay_client import RemoteWorkerRelay


async def run_chunk(relay: RemoteWorkerRelay, chunk: str, *, max_tokens: int, index: int, total: int) -> dict:
    os.environ["DEID_LLM_MAX_TOKENS"] = str(max_tokens)
    logs: list[str] = []
    raw_tokens: list[str] = []

    def on_event(ev: dict) -> None:
        if ev.get("type") == "log":
            logs.append(str(ev.get("line", "")))
        if ev.get("type") == "token":
            raw_tokens.append(str(ev.get("content", "")))

    result = await discover_llm(
        chunk,
        relay,
        job_id=99999,
        system_prompt=build_default_scan_prompt(),
        on_event=on_event,
    )
    content = "".join(raw_tokens)
    _, fmt = parse_llm_entities(content, frozenset({"company", "person", "org", "id"}))
    return {
        "max_tokens": max_tokens,
        "index": index,
        "chunk_chars": len(chunk),
        "entities": len(result.entities),
        "format": fmt,
        "errors": result.errors,
        "elapsed_ms": result.elapsed_ms,
        "completion_est": result.completion_tokens,
        "output_chars": len(content),
        "output_lines": content.count("\n") + (1 if content.strip() else 0),
        "output_tail": content.strip()[-120:] if content.strip() else "",
        "logs": logs,
        "names": [e.canonical_name for e in result.entities[:8]],
    }


async def main() -> None:
    doc = ROOT / "tests" / "fixtures" / "ceec_audit_test.docx"
    if not doc.exists():
        doc = ROOT / "tests" / "fixtures" / "spic_sample.docx"
    if not doc.exists():
        print("ERROR: no fixture docx found")
        sys.exit(1)

    relay = RemoteWorkerRelay()
    await relay.refresh_status()
    sess = relay.session
    if not sess or sess.state != "ready":
        print(f"ERROR: worker not ready: {relay.status_dict()}")
        sys.exit(1)
    print(f"Worker: {sess.model} @ {sess.hostname} ({sess.state})")

    sample = extract_sample_text(doc)
    chunk_size = int(os.getenv("DEID_LLM_CHUNK_SIZE", "4000"))
    chunks = _chunk_text(sample, chunk_size, 300)
    print(f"Doc: {doc.name} | sample={len(sample)} chars | chunks={len(chunks)} | chunk_size={chunk_size}")

    # Run first 2 chunks at default max_tokens
    default_max = int(os.getenv("DEID_LLM_MAX_TOKENS", "1024"))
    for i, chunk in enumerate(chunks[:2]):
        print(f"\n{'='*60}")
        print(f"Chunk {i+1}/{len(chunks)} preview: {chunk[:80].replace(chr(10), ' ')}…")
        r = await run_chunk(relay, chunk, max_tokens=default_max, index=i + 1, total=len(chunks))
        print(f"max_tokens={r['max_tokens']} | entities={r['entities']} | fmt={r['format']} | "
              f"out={r['output_chars']} chars / ~{r['completion_est']} tok | {r['elapsed_ms']}ms")
        if r["errors"]:
            print(f"errors: {r['errors']}")
        for line in r["logs"]:
            print(f"  log: {line}")
        if r["names"]:
            print("  sample:", ", ".join(r["names"]))
        if r["output_tail"]:
            print(f"  tail: …{r['output_tail']}")

    # Compare max_tokens on chunk 1 only if we have time
    if len(chunks) >= 1:
        print(f"\n{'='*60}")
        print("max_tokens sweep on chunk 1 (512 vs 1024 vs 2048):")
        sweep = []
        for mt in (512, 1024, 2048):
            r = await run_chunk(relay, chunks[0], max_tokens=mt, index=1, total=len(chunks))
            sweep.append(r)
            print(f"  max_tokens={mt:4d} -> entities={r['entities']:2d}  out_chars={r['output_chars']:4d}  fmt={r['format']}")
        counts = [s["entities"] for s in sweep]
        if counts[0] < counts[1] < counts[2]:
            print("  => 1024 may be truncating; consider raising DEID_LLM_MAX_TOKENS")
        elif counts[0] == counts[1] == counts[2]:
            print("  => entity count stable across limits; 1024 is sufficient for this chunk")
        else:
            print(f"  => mixed: {dict(zip([512,1024,2048], counts))}")


if __name__ == "__main__":
    asyncio.run(main())
