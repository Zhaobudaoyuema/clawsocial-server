"""Deep pipeline Worker flows: detect + suggest."""

from __future__ import annotations



import os

import re

import uuid

from collections.abc import Callable

from typing import Any



from app.deid.discovery.flow_parse import parse_risk_lines, parse_suggest_line

from app.deid.discovery.flows import (
    FlowItem,
    default_chunk_user_message,
    run_worker_flow,
    worker_max_tokens_detect,
    worker_max_tokens_suggest,
)
from app.deid.discovery.llm import apply_scan_chunk_plan, build_llm_chunks

from app.deid.discovery.semantic_rules import (
    apply_default_rewrites,
    default_semantic_rewrite,
    extract_program_risks,
    merge_program_and_worker_risks,
    validate_suggest_rewrite,
)

from app.deid.prompts import FLOW_DEEP_DETECT_KEY, FLOW_DEEP_SUGGEST_KEY, JOB_EXTRA_SEPARATOR

from app.deid.settings_store import get_flow_prompt



_flow_chunk_log_re = re.compile(

    r"\[deep_detect\] 第 (\d+)/(\d+) 段，解析 (\d+) 条"

)



_MAX_RISKS_PER_UNIT = 3

_PLACEHOLDER_RISK = re.compile(
    r"^\[公司_\d+\](?:\([^)]*\))?$|^\[姓名_\d+\](?:\([^)]*\))?$"
)
_GENERIC_HEADERS = frozenset(
    {
        "公司名称",
        "流通a股",
        "流通b股",
        "流通h股",
        "金额单位",
        "法定代表人",
        "审计对象",
        "被审计单位",
    }
)
_BOILERPLATE_PATTERNS = (
    re.compile(r"导致.*风险警示"),
    re.compile(r"取数口径"),
    re.compile(r"公司拟采取.*应对"),
)


def _reject_low_quality_risk(original: str) -> bool:
    """Reject obvious false positives (placeholders, headers, boilerplate)."""
    s = original.strip()
    if not s:
        return True
    if _PLACEHOLDER_RISK.match(s):
        return True
    if s.casefold() in _GENERIC_HEADERS:
        return True
    if re.fullmatch(r"\[公司_\d+\](?:\([^)]*\))?", s):
        return True
    if re.search(r"\[公司_\d+\]", s) and len(s) <= 36:
        return True
    return any(p.search(s) for p in _BOILERPLATE_PATTERNS)


def deep_detect_user_message(unit: FlowItem, index: int, total: int) -> str:
    head = (
        f"【片段 {index}/{total}，约 {len(unit.text)} 字】\n"
        "【说明】以下文本已完成名称替换（[公司_x][姓名_x]）。"
        "请只找可推断具体公司身份的语义指纹；"
        "不要报告占位符、通用表头、未替换的公司字面或披露模板句。\n"
    )
    return f"{head}{unit.text}"





def _suggest_context() -> int:

    return int(os.getenv("DEID_DEEP_SUGGEST_CONTEXT", "300"))





def _assign_risk_ids(risks: list[dict]) -> list[dict]:

    out: list[dict] = []

    seen: set[str] = set()

    for item in risks:

        original = item.get("original") or ""

        key = f"{item.get('category', '')}\0{original}"

        if key in seen:

            continue

        seen.add(key)

        rewrite = item.get("rewrite") or item.get("suggested_rewrite")

        risk_id = item.get("risk_id") or f"r-{uuid.uuid4().hex[:8]}"

        out.append(

            {

                "risk_id": risk_id,

                "category": item.get("category"),

                "original": original,

                "note": item.get("note", ""),

                "window_id": item.get("window_id"),

                "source": item.get("source", "worker"),

                "enabled": item.get("enabled", True),

                "suggested_rewrite": rewrite,

                "rewritten": rewrite,

                "writable": item.get("writable"),

            }

        )

    return out





def _validate_verbatim(window_text: str, original: str) -> bool:

    return bool(original) and original in window_text





def _reject_cross_paragraph(original: str) -> bool:

    return "\n" in original or "\r" in original





def _mark_writable(risks: list[dict], preview_text: str) -> list[dict]:

    for item in risks:

        orig = item.get("original") or ""

        if item.get("writable") is None:

            writable = (

                bool(orig)

                and not _reject_cross_paragraph(orig)

                and any(orig in line for line in preview_text.split("\n"))

            )

            item["writable"] = writable

    return risks





def _build_detect_units(
    preview_text: str,
    *,
    scan_chunk_plan: dict | None = None,
) -> tuple[list[FlowItem], dict]:
    """Reuse entity-scan chunk boundaries; never re-segment into per-line windows."""
    if not preview_text.strip():
        return [], {"chunks": 0, "units": 0, "mode": "empty"}
    if scan_chunk_plan:
        chunks = apply_scan_chunk_plan(preview_text, scan_chunk_plan)
        mode = "scan_chunks_reuse"
    else:
        chunks = build_llm_chunks(preview_text)
        mode = "scan_chunks"
    units = [
        FlowItem(text=c, meta={"window_id": f"chunk-{i + 1}", "kind": "chunk"})
        for i, c in enumerate(chunks)
    ]
    return units, {
        "chunks": len(chunks),
        "units": len(units),
        "mode": mode,
    }





async def run_deep_detect(

    sample: str,

    router,

    db,

    *,

    job_id: int,

    job_extra: str | None = None,

    scan_chunk_plan: dict | None = None,

    on_progress=None,

    on_event: Callable[[dict], None] | None = None,

) -> tuple[list[dict], dict]:

    """Flow 5: semantic fingerprint detection on entity-preview text."""



    def emit(event: dict) -> None:

        if on_event:

            on_event(event)



    preview_text = sample

    program_risks = extract_program_risks(preview_text)

    if program_risks:

        emit({"type": "log", "line": f"程序规则预检：{len(program_risks)} 条"})



    units, unit_meta = _build_detect_units(
        preview_text, scan_chunk_plan=scan_chunk_plan
    )

    if not units:

        emit({"type": "log", "line": "文档无内容，跳过语义检测"})

        merged = _assign_risk_ids(_mark_writable(program_risks, preview_text))

        return merged, {**unit_meta, "chunks": 0, "risks": len(merged), "program": len(program_risks)}



    chunk_n = len(units)
    reuse = unit_meta.get("mode") == "scan_chunks_reuse"
    emit(
        {
            "type": "log",
            "line": (
                f"复用实体扫描切段，共 {chunk_n} 段"
                if reuse and chunk_n > 1
                else (
                    f"文档将分 {chunk_n} 段分析"
                    if chunk_n > 1
                    else "文档较短，单段分析"
                )
            ),
        }
    )

    emit({"type": "stats", "chunks": len(units)})



    prompt = get_flow_prompt(db, FLOW_DEEP_DETECT_KEY)

    if job_extra:

        prompt = f"{prompt}{JOB_EXTRA_SEPARATOR}{job_extra.strip()}"



    rejected_cross = 0
    rejected_low_quality = 0



    def parse_chunk(content: str, unit: FlowItem) -> list[dict]:

        nonlocal rejected_cross, rejected_low_quality

        parsed = parse_risk_lines(content)

        valid = []

        for item in parsed[:_MAX_RISKS_PER_UNIT]:

            original = item.get("original") or ""

            if _reject_cross_paragraph(original):

                rejected_cross += 1

                continue

            if _reject_low_quality_risk(original):

                rejected_low_quality += 1

                continue

            if _validate_verbatim(unit.text, original):

                item["window_id"] = unit.meta.get("window_id")

                item["source"] = "worker"

                valid.append(item)

        for item in valid:

            emit(

                {

                    "type": "risk",

                    "category": item.get("category"),

                    "original": str(item.get("original") or ""),

                }

            )

        return valid



    def bridge(ev: dict) -> None:

        ev_type = ev.get("type")

        if ev_type == "flow_chunk_start":

            idx = int(ev.get("index") or 0)

            total = int(ev.get("total") or 0)

            emit({"type": "chunk_start", "index": idx, "total": total})

            emit({"type": "log", "line": f"开始分析第 {idx}/{total} 段…"})

            return

        if ev_type == "log":

            line = str(ev.get("line") or "")

            m = _flow_chunk_log_re.search(line)

            if m:

                emit(

                    {

                        "type": "log",

                        "line": (

                            f"第 {m.group(1)}/{m.group(2)} 段完成，"

                            f"本段发现 {m.group(3)} 条语义风险"

                        ),

                    }

                )

                return

        emit(ev)



    result = await run_worker_flow(

        "deep_detect",

        units,

        router,

        job_id=job_id,

        db=db,

        system_prompt=prompt,

        build_user_message=deep_detect_user_message,

        parse_chunk=parse_chunk,

        max_tokens=worker_max_tokens_detect(),

        on_progress=on_progress,

        on_event=bridge,

    )

    worker_risks = _assign_risk_ids(result.items)

    merged = merge_program_and_worker_risks(program_risks, worker_risks)
    merged = apply_default_rewrites(merged)
    merged = _mark_writable(merged, preview_text)

    summary = {

        **unit_meta,

        "chunks": len(units),

        "risks": len(merged),

        "program": len(program_risks),

        "worker": len(worker_risks),

        "rejected_cross_paragraph": rejected_cross,
        "rejected_low_quality": rejected_low_quality,

        "skipped": result.skipped,

        "errors": result.errors,

        "elapsed_ms": result.elapsed_ms,

    }

    if merged:

        emit({"type": "log", "line": f"语义检测汇总：共 {len(merged)} 条风险"})

    else:

        emit({"type": "log", "line": "语义检测完成，未发现语义指纹"})

    return merged, summary





async def run_deep_suggest(

    risk: dict,

    sample: str,

    router,

    db,

    *,

    job_id: int,

    on_event: Callable[[dict], None] | None = None,

) -> str | None:

    """Flow 6: single-risk rewrite suggestion."""

    original = risk.get("original") or ""

    if not original or not router:

        return None



    ctx = _suggest_context()

    idx = sample.find(original)

    if idx < 0:

        before = ""

        after = sample[: ctx * 2]

    else:

        before = sample[max(0, idx - ctx) : idx]

        after = sample[idx + len(original) : idx + len(original) + ctx]



    user_msg = (

        f"【待改写】\n{original}\n\n"

        f"【前文】\n{before}\n\n"

        f"【后文】\n{after}"

    )[:800]

    prompt = get_flow_prompt(db, FLOW_DEEP_SUGGEST_KEY)



    units = [FlowItem(text=user_msg)]



    def parse_chunk(content: str, unit: FlowItem) -> list[str]:

        s = parse_suggest_line(content)

        return [s] if s else []



    result = await run_worker_flow(

        "deep_suggest",

        units,

        router,

        job_id=job_id,

        db=db,

        system_prompt=prompt,

        build_user_message=lambda u, i, t: u.text,

        parse_chunk=parse_chunk,

        max_tokens=worker_max_tokens_suggest(),

        on_event=on_event,

    )

    if result.items:

        return result.items[0]

    return None





async def run_deep_suggest_all(

    risks: list[dict],

    sample: str,

    router,

    db,

    *,

    job_id: int,

    on_progress: Callable[[int, int], None] | None = None,

    on_event: Callable[[dict], None] | None = None,

    skip_existing: bool = True,

) -> list[dict]:

    """Generate rewrite suggestions for each detected risk."""



    def emit(event: dict) -> None:

        if on_event:

            on_event(event)



    out: list[dict] = []

    pending = [

        r

        for r in risks

        if not (skip_existing and (r.get("suggested_rewrite") or r.get("rewritten")))

    ]

    total = len(pending)

    if total == 0:

        return list(risks)



    preset = len(risks) - total
    if preset:
        emit({"type": "log", "line": f"{preset} 条已有规则改写，{total} 条待 Worker 补生成…"})
    else:
        emit({"type": "log", "line": f"开始为 {total} 条指纹生成改写建议…"})



    done = 0

    for risk in risks:

        if skip_existing and (risk.get("suggested_rewrite") or risk.get("rewritten")):

            out.append(risk)

            continue

        done += 1

        if on_progress:

            on_progress(done, total)

        original = str(risk.get("original") or "")

        label = original if len(original) <= 36 else f"{original[:36]}…"

        updated = dict(risk)
        category = str(risk.get("category") or "")
        rule_rewrite = default_semantic_rewrite(category, original)
        if rule_rewrite and rule_rewrite != original:
            updated["suggested_rewrite"] = rule_rewrite
            updated["rewritten"] = rule_rewrite
            short = rule_rewrite if len(rule_rewrite) <= 48 else f"{rule_rewrite[:48]}…"
            emit({"type": "log", "line": f"改写 [{done}/{total}]：{label} → {short}（规则）"})
            out.append(updated)
            continue

        emit({"type": "log", "line": f"改写 [{done}/{total}]：{label}"})

        suggestion = await run_deep_suggest(
            risk,
            sample,
            router,
            db,
            job_id=job_id,
            on_event=on_event,
        )

        if suggestion and validate_suggest_rewrite(category, original, suggestion):
            updated["suggested_rewrite"] = suggestion
            updated["rewritten"] = suggestion
            short = suggestion if len(suggestion) <= 48 else f"{suggestion[:48]}…"
            emit({"type": "log", "line": f"  → {short}"})
        elif rule_rewrite and rule_rewrite != original:
            updated["suggested_rewrite"] = rule_rewrite
            updated["rewritten"] = rule_rewrite
            emit({"type": "log", "line": f"  → {rule_rewrite}（规则兜底）"})
        else:
            emit({"type": "log", "line": "  → 未能自动生成改写"})

        out.append(updated)



    return out





def find_risk_by_id(risks: list[dict], risk_id: str) -> dict | None:

    for r in risks:

        if r.get("risk_id") == risk_id:

            return r

    return None





def update_risk_in_list(risks: list[dict], risk_id: str, patch: dict[str, Any]) -> list[dict]:

    out = []

    for r in risks:

        if r.get("risk_id") == risk_id:

            merged = {**r, **patch}

            out.append(merged)

        else:

            out.append(r)

    return out


