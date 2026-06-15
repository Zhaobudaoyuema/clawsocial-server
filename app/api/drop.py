"""
File Drop API: passcode-protected upload + public file listing.
独立于用户认证体系，口令保护上传，公开浏览下载。
"""
import logging

from fastapi import APIRouter, Depends, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DroppedFile
from app.uploads import save_drop_upload

router = APIRouter(prefix="/api/drop", tags=["drop"])
logger = logging.getLogger(__name__)

# 口令写死在此，agent skill 知道口令即可使用
DROP_PASSCODE = "claw2026drop"


def _validate_passcode(passcode: str) -> None:
    """校验 drop 口令。错误返回 401。"""
    if passcode != DROP_PASSCODE:
        raise HTTPException(status_code=401, detail="口令错误")


@router.post("/upload")
async def drop_upload(
    file: UploadFile,
    source: str = Form("web"),
    x_drop_passcode: str = Header(..., alias="X-Drop-Passcode", description="Drop 口令"),
    db: Session = Depends(get_db),
):
    """
    上传文件到 File Drop。需要口令，不需要用户账号。
    返回 JSON（非 text/plain），方便前端和 agent 解析。
    """
    _validate_passcode(x_drop_passcode)

    if not file.filename:
        raise HTTPException(status_code=400, detail="请提供文件")

    url, stored_path, original, file_size = await save_drop_upload(file)

    record = DroppedFile(
        original_filename=original,
        stored_path=stored_path,
        file_size=file_size,
        source=source,
        url=url,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "ok": True,
        "url": url,
        "filename": original,
        "size": file_size,
        "source": source,
    }


@router.get("/files")
def drop_files(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """
    公开查看已上传文件列表。无需认证。
    """
    limit = min(limit, 200)
    total = db.query(func.count(DroppedFile.id)).scalar() or 0
    rows = (
        db.query(DroppedFile)
        .order_by(DroppedFile.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {
        "files": [
            {
                "id": r.id,
                "filename": r.original_filename,
                "size": r.file_size,
                "source": r.source,
                "url": r.url,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
    }
