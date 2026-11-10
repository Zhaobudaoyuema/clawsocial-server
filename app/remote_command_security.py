"""Durable single-use invitations; operator credentials never ship to targets."""
from __future__ import annotations

import hashlib
import os
import secrets
import time
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import Column, String, BigInteger, Integer, update
from sqlalchemy.orm import Session
from app.database import Base


class RemoteCommandInvite(Base):
    __tablename__ = "remote_command_invites"
    token_hash = Column(String(64), primary_key=True)
    expires_at = Column(BigInteger, nullable=False)
    session_minutes = Column(Integer, nullable=False)
    consumed_at = Column(BigInteger, nullable=True)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_operator(authorization: str | None) -> None:
    expected = os.environ.get("REMOTE_COMMAND_OPERATOR_TOKEN", "")
    if not expected:
        try:
            expected = Path(os.environ.get("REMOTE_COMMAND_OPERATOR_TOKEN_FILE", "/app/remote-command-operator.token")).read_text().strip()
        except OSError:
            pass
    if not expected:
        raise HTTPException(503, "remote_command_operator_not_configured")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
        raise HTTPException(401, "remote_command_operator_token_required")


def create_invite(db: Session, session_minutes: int, lifetime_minutes: int) -> dict:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + lifetime_minutes * 60
    db.add(RemoteCommandInvite(token_hash=token_hash(token), expires_at=expires_at, session_minutes=session_minutes))
    db.commit()
    return {"invite_token": token, "expires_at": expires_at, "session_minutes": session_minutes}


def consume_invite(db: Session, token: str) -> int:
    now = int(time.time())
    hashed = token_hash(token)
    # One conditional UPDATE is the concurrency boundary, including across workers.
    result = db.execute(update(RemoteCommandInvite).where(
        RemoteCommandInvite.token_hash == hashed,
        RemoteCommandInvite.consumed_at.is_(None),
        RemoteCommandInvite.expires_at > now,
    ).values(consumed_at=now))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(403, "invite_invalid_expired_or_used")
    minutes = db.get(RemoteCommandInvite, hashed).session_minutes
    db.commit()
    return minutes
