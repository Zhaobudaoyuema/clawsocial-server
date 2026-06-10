"""Programmatic extraction of deep-scan candidate windows from de-identified text."""
from __future__ import annotations

import os
import re
import uuid

_FIELD_KEYWORDS = re.compile(
    r"客户|项目|主体|股东|高管|编号|法定代表人|统一社会信用|被审计|审计对象|委托人"
)
_PROJECT_PATTERN = re.compile(
    r"\d{4,}.*(?:内控|审计|项目)|项目(?:编号|名称|代号)|报告编号"
)
_PERSON_PLACEHOLDER = re.compile(r"\[姓名_\d+\].*\d{4}")
_ORG_FINGERPRINT = re.compile(r"[省市自治区].{0,12}\d{2,}")
_STOCK_CODE = re.compile(r"\d{6}\.[A-Z]{2,4}")
_PROJECT_NAME = re.compile(
    r"MW|光热|压缩空气储能|风电项目|多能互补|绿电示范|储能电站"
)
_DEAL_EVENT = re.compile(r"收购兼并|拖欠|融资租赁|股权转让|诉讼")
_LISTING_STRUCTURE = re.compile(r"流通A股|流通H股|A\+H|＋H")


def _window_size() -> int:
    return int(os.getenv("DEID_DEEP_WINDOW_SIZE", "400"))


def _line_is_candidate(line: str) -> bool:
    s = line.strip()
    if not s or len(s) < 4:
        return False
    if _FIELD_KEYWORDS.search(s):
        return True
    if _PROJECT_PATTERN.search(s):
        return True
    if _PERSON_PLACEHOLDER.search(s):
        return True
    if _ORG_FINGERPRINT.search(s):
        return True
    if _STOCK_CODE.search(s):
        return True
    if _PROJECT_NAME.search(s):
        return True
    if _DEAL_EVENT.search(s):
        return True
    if _LISTING_STRUCTURE.search(s):
        return True
    return False


def extract_deep_candidates(text: str, *, window_size: int | None = None) -> list[dict]:
    """
    Extract candidate windows for deep_detect.

    Returns list of {window_id, text, char_start, char_end}.
    """
    if not text:
        return []
    size = window_size or _window_size()
    lines = text.split("\n")
    windows: list[dict] = []
    char_pos = 0
    buf: list[str] = []
    buf_start = 0

    def flush(end_pos: int) -> None:
        nonlocal buf, buf_start
        if not buf:
            return
        chunk = "\n".join(buf).strip()
        if chunk:
            windows.append(
                {
                    "window_id": f"w-{uuid.uuid4().hex[:8]}",
                    "text": chunk[:size],
                    "char_start": buf_start,
                    "char_end": min(end_pos, buf_start + len(chunk)),
                }
            )
        buf = []

    for line in lines:
        line_start = char_pos
        line_end = char_pos + len(line)
        if _line_is_candidate(line):
            if not buf:
                buf_start = line_start
            buf.append(line)
            joined = "\n".join(buf)
            if len(joined) >= size:
                flush(line_end)
                buf_start = line_end + 1
        else:
            if buf:
                flush(line_start)
        char_pos = line_end + 1

    if buf:
        flush(char_pos)

    seen_text: set[str] = set()
    deduped: list[dict] = []
    for w in windows:
        key = w["text"].strip()
        if key and key not in seen_text:
            seen_text.add(key)
            deduped.append(w)
    return deduped
