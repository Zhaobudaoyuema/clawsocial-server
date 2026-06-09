"""Dense sample max_tokens sweep."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deid.discovery.llm import discover_llm
from app.deid.prompts import build_default_scan_prompt
from app.deid.worker.relay_client import RemoteWorkerRelay

SAMPLE = (
    """中国能源建设股份有限公司（以下简称「中国能建」）2024年度项目风险识别报告。
审计对象包括中国能源建设集团有限公司、中能建氢能源有限公司、中国电力工程顾问集团有限公司。
项目负责人：张伟、李明。统一社会信用代码：91110000123456789X。
关联方包括北京能源投资集团有限责任公司、国家电网有限公司华东分公司。
本报告由天健会计师事务所（特殊普通合伙）出具，不涉及该所名称脱敏。
"""
    * 8
)


async def one(relay: RemoteWorkerRelay, max_tok: int) -> dict:
    os.environ["DEID_LLM_MAX_TOKENS"] = str(max_tok)
    parts: list[str] = []

    def on_event(ev: dict) -> None:
        if ev.get("type") == "token":
            parts.append(str(ev.get("content", "")))

    r = await discover_llm(
        SAMPLE,
        relay,
        job_id=888,
        system_prompt=build_default_scan_prompt(),
        on_event=on_event,
    )
    raw = "".join(parts)
    return {
        "max_tokens": max_tok,
        "entities": len(r.entities),
        "raw": raw,
        "names": [e.canonical_name for e in r.entities],
        "errors": r.errors,
        "ms": r.elapsed_ms,
        "out_chars": len(raw),
    }


async def main() -> None:
    relay = RemoteWorkerRelay()
    await relay.refresh_status()
    if not relay.session or relay.session.state != "ready":
        print("worker not ready")
        sys.exit(1)

    rows = []
    for mt in (256, 512, 1024, 2048):
        rows.append(await one(relay, mt))

    out_path = ROOT / "logs" / "llm_sim_dense.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    for row in rows:
        print(
            f"max_tokens={row['max_tokens']} entities={row['entities']} "
            f"chars={row['out_chars']} ms={row['ms']}"
        )
        print(f"  raw: {row['raw'][:300]!r}")
        print(f"  names: {row['names']}")


if __name__ == "__main__":
    asyncio.run(main())
