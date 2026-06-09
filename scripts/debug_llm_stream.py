"""Debug stream token count vs non-stream full body."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deid.prompts import build_default_scan_prompt, build_scan_user_message
from app.deid.worker.relay_client import RemoteWorkerRelay

SAMPLE = """中国能源建设股份有限公司（以下简称「中国能建」）2024年度项目风险识别报告。
审计对象包括中国能源建设集团有限公司、中能建氢能源有限公司、中国电力工程顾问集团有限公司。
项目负责人：张伟、李明。"""


async def main() -> None:
    relay = RemoteWorkerRelay()
    await relay.refresh_status()
    sess = relay.session
    assert sess and sess.state == "ready"

    system = build_default_scan_prompt()
    user = build_scan_user_message(SAMPLE, index=1, total=1)
    base_body = {
        "model": sess.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "reasoning_effort": "none",
        "temperature": 0,
        "max_tokens": 1024,
    }

    # Stream
    tokens: list[str] = []
    async for t in relay.chat_completions_stream({**base_body, "stream": True}, request_id="dbg-stream"):
        tokens.append(t)
    stream_text = "".join(tokens)

    # Non-stream
    ns = await relay.chat_completions({**base_body, "stream": False}, request_id="dbg-ns")
    choices = ns.get("choices") or []
    ns_text = ""
    if choices:
        ns_text = (choices[0].get("message") or {}).get("content") or ""

    out = {
        "stream_events": len(tokens),
        "stream_chars": len(stream_text),
        "stream_text": stream_text,
        "nonstream_chars": len(ns_text),
        "nonstream_text": ns_text,
        "finish_reason": choices[0].get("finish_reason") if choices else None,
        "usage": ns.get("usage"),
    }
    path = ROOT / "logs" / "llm_stream_debug.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
