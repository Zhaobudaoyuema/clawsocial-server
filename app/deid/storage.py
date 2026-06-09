"""Per-job upload directories under uploads/deid/{job_id}/."""
import os
import re
import shutil
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.uploads import UPLOADS_DIR, MAX_FILE_SIZE

DEID_ROOT = UPLOADS_DIR / "deid"
JOB_RETENTION_HOURS = 8


def job_dir(job_id: int) -> Path:
    p = DEID_ROOT / str(job_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sanitize_filename(name: str) -> str:
    base = os.path.basename(name or "document.docx")
    safe = re.sub(r"[^\w\s\-\.]", "_", base, flags=re.IGNORECASE)
    return safe.strip() or "document.docx"


async def save_job_docx(job_id: int, file: UploadFile) -> tuple[str, str]:
    """Save uploaded docx; returns (stored_relative_path, original_filename)."""
    original = file.filename or "document.docx"
    if not original.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 文件")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过限制")
    safe = _sanitize_filename(original)
    dest = job_dir(job_id) / f"original_{safe}"
    dest.write_bytes(content)
    rel = str(dest.relative_to(UPLOADS_DIR)).replace("\\", "/")
    return rel, original


def resolve_upload_path(stored_path: str) -> Path:
    return UPLOADS_DIR / stored_path.replace("/", os.sep)


def delete_job_files(job_id: int) -> None:
    d = DEID_ROOT / str(job_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
