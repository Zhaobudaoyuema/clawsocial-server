"""In-memory chat sessions for deid local dialogue."""
from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.deid.engine.pipeline import extract_sample_text
from app.deid.prompts import CHAT_DEFAULT_SYSTEM
from app.deid.storage import resolve_upload_path
from app.models_deid import DeidJob

SESSION_TTL = timedelta(hours=2)
MAX_DOC_CHARS = 50000


@dataclass
class ChatSession:
    id: str
    messages: list[dict] = field(default_factory=list)
    doc_text: str | None = None
    doc_label: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ChatSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        expired = [
            sid
            for sid, s in self._sessions.items()
            if now - s.created_at > SESSION_TTL
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def get(self, session_id: str) -> ChatSession | None:
        session = self._sessions.get(session_id)
        if not session:
            return None
        if datetime.now(timezone.utc) - session.created_at > SESSION_TTL:
            del self._sessions[session_id]
            return None
        return session

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    async def create(
        self,
        db: Session,
        *,
        mode: str,
        job_id: int | None = None,
        file: UploadFile | None = None,
    ) -> ChatSession:
        doc_text: str | None = None
        doc_label: str | None = None

        if mode == "none":
            pass
        elif mode == "job":
            if job_id is None:
                raise HTTPException(400, "job_id 必填")
            job = db.get(DeidJob, job_id)
            if not job or not job.stored_path:
                raise HTTPException(404, "任务不存在或无文件")
            path = resolve_upload_path(job.stored_path)
            if not path.exists():
                raise HTTPException(400, "原文件已丢失")
            doc_text = extract_sample_text(path)[:MAX_DOC_CHARS]
            doc_label = job.original_filename
        elif mode == "upload":
            if not file or not file.filename:
                raise HTTPException(400, "请上传 docx 文件")
            if not file.filename.lower().endswith(".docx"):
                raise HTTPException(400, "仅支持 .docx")
            suffix = Path(file.filename).suffix
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = Path(tmp.name)
            try:
                doc_text = extract_sample_text(tmp_path)[:MAX_DOC_CHARS]
                doc_label = file.filename
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            raise HTTPException(400, "mode 无效")

        session = ChatSession(
            id=uuid.uuid4().hex,
            doc_text=doc_text,
            doc_label=doc_label,
        )
        self._sessions[session.id] = session
        return session

    def build_messages(self, session: ChatSession, user_text: str) -> list[dict]:
        system = CHAT_DEFAULT_SYSTEM
        if session.doc_text:
            system += f"\n\n【参考文档：{session.doc_label}】\n{session.doc_text}"
        return (
            [{"role": "system", "content": system}]
            + list(session.messages)
            + [{"role": "user", "content": user_text}]
        )

    def append_exchange(self, session: ChatSession, user_text: str, assistant_text: str) -> None:
        session.messages.append({"role": "user", "content": user_text})
        session.messages.append({"role": "assistant", "content": assistant_text})

    def session_meta(self, session: ChatSession) -> dict:
        return {
            "session_id": session.id,
            "doc_label": session.doc_label,
            "has_doc": session.doc_text is not None,
            "message_count": len(session.messages),
            "messages": session.messages,
            "created_at": session.created_at.isoformat(),
        }


def list_chat_jobs(db: Session) -> list[dict]:
    """Jobs with stored files for chat document picker."""
    rows = (
        db.query(DeidJob)
        .filter(DeidJob.stored_path.isnot(None))
        .order_by(DeidJob.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": j.id,
            "status": j.status,
            "original_filename": j.original_filename,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in rows
    ]
