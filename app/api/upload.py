"""
通用文件上传接口：上传任意文件，返回在线 URL。
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse

from app.utils import plain_text
from app.uploads import save_upload, MAX_FILE_SIZE
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

router = APIRouter(tags=["upload"])
logger = logging.getLogger(__name__)


def _auth(x_token: str, db: Session) -> User:
    user = db.query(User).filter(User.token == x_token).first()
    if not user:
        raise HTTPException(status_code=401, detail="Token 无效")
    return user


@router.post("/api/upload")
async def upload_file(
    request: Request,
    file: UploadFile,
    x_token: str = Header(..., alias="X-Token", description="注册成功后返回的 Token"),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """
    通用文件上传：上传文件后返回在线访问 URL。
    文件公开可访问（无需鉴权即可下载）。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="请提供文件")

    user = _auth(x_token, db)
    url, stored_name, original = await save_upload(file, user_id=user.id, request=request)

    return plain_text(url)
