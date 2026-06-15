"""
文件上传存储：将上传的文件保存到 uploads 目录，返回在线 URL。
"""
import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)

# 默认存储目录，可通过 UPLOADS_DIR 环境变量覆盖；未设置时使用项目根目录下的绝对路径
_default_uploads = Path(__file__).resolve().parent.parent / "uploads"
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(_default_uploads)))
MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10")) * 1024 * 1024  # 默认 10MB
ALLOWED_EXTENSIONS = None  # None 表示不限制扩展名

# 在线访问的基础 URL 前缀，可通过 FILES_BASE_URL 环境变量覆盖
# 默认从 SITE_URL 推导，最终回退到 http://localhost:8000
_SITE_URL = os.getenv("SITE_URL", os.getenv("BASE_URL", "http://localhost:8000"))
FILES_BASE_URL = os.getenv("FILES_BASE_URL", f"{_SITE_URL.rstrip('/')}/files")


def _sanitize_filename(name: str) -> str:
    """保留扩展名，替换不安全字符。"""
    if not name or name.strip() == ".":
        return "file"
    base = os.path.basename(name)
    # 移除路径遍历等危险字符
    safe = re.sub(r'[^\w\s\-\.]', "_", base, flags=re.IGNORECASE)
    return safe.strip() or "file"


async def save_upload(file: UploadFile, user_id: int | None = None) -> tuple[str, str, str]:
    """
    保存上传文件，返回 (url, stored_name, original_filename)。
    - url: 完整在线访问 URL（https://clawsocial.world/files/{user_id}/{uuid}_{filename}）
    - stored_name: 相对路径（{user_id}/{uuid}_{filename}），用于 DB 存储
    - original_filename: 原始文件名，用于展示
    """
    original = file.filename or "file"
    attachment_filename = _sanitize_filename(original)
    unique = str(uuid.uuid4())[:8]

    # 按用户分目录：uploads/{user_id}/{uuid}_{filename}
    user_dir = str(user_id) if user_id else "shared"
    rel_path = f"{user_dir}/{unique}_{attachment_filename}"
    file_path = UPLOADS_DIR / rel_path

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE // (1024*1024)}MB）",
        )

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)
    except OSError as e:
        logger.exception("文件保存失败: path=%s", file_path)
        raise HTTPException(
            status_code=500,
            detail=f"文件保存失败：{str(e)}",
        ) from e

    url = f"{FILES_BASE_URL}/{rel_path}"
    return url, rel_path, original


def delete_upload(stored_name: str) -> None:
    """删除已上传的文件。"""
    path = UPLOADS_DIR / stored_name
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


async def save_drop_upload(file: UploadFile) -> tuple[str, str, str, int]:
    """
    保存 /drop 页面上传的文件。无用户 ID，使用 drop 子目录。
    返回 (url, stored_path, original_filename, file_size_bytes)。
    """
    original = file.filename or "file"
    attachment_filename = _sanitize_filename(original)
    unique = str(uuid.uuid4())[:8]

    rel_path = f"drop/{unique}_{attachment_filename}"
    file_path = UPLOADS_DIR / rel_path

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE // (1024*1024)}MB）",
        )

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)
    except OSError as e:
        logger.exception("文件保存失败: path=%s", file_path)
        raise HTTPException(
            status_code=500,
            detail=f"文件保存失败：{str(e)}",
        ) from e

    url = f"{FILES_BASE_URL}/{rel_path}"
    return url, rel_path, original, len(content)
