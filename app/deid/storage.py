"""Per-job upload directories under uploads/deid/{job_id}/."""
import os
import re
import shutil
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.deid.convert import SUPPORTED_EXTENSIONS, ensure_source_markdown, extension_allowed
from app.uploads import UPLOADS_DIR, MAX_FILE_SIZE

DEID_ROOT = UPLOADS_DIR / "deid"
JOB_RETENTION_HOURS = 8
MAPPING_RETENTION_DAYS = 90


def job_dir(job_id: int) -> Path:
    p = DEID_ROOT / str(job_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sanitize_filename(name: str) -> str:
    base = os.path.basename(name or "document")
    safe = re.sub(r"[^\w\s\-\.]", "_", base, flags=re.IGNORECASE)
    return safe.strip() or "document"


async def save_job_file(job_id: int, file: UploadFile) -> tuple[str, str, Path]:
    """
    Save uploaded file and convert to source.md.
    Returns (stored_relative_path to source.md, original_filename, original_path).
    """
    original = file.filename or "document"
    if not extension_allowed(original):
        exts = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"不支持的文件格式，仅支持：{exts}")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过限制")
    safe = _sanitize_filename(original)
    jdir = job_dir(job_id)
    original_path = jdir / f"original_{safe}"
    original_path.write_bytes(content)
    ensure_source_markdown(original_path, jdir)
    md_path = jdir / "source.md"
    rel = str(md_path.relative_to(UPLOADS_DIR)).replace("\\", "/")
    return rel, original, original_path


def resolve_upload_path(stored_path: str) -> Path:
    return UPLOADS_DIR / stored_path.replace("/", os.sep)


def delete_job_files(job_id: int) -> None:
    d = DEID_ROOT / str(job_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
