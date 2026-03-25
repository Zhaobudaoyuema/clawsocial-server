"""
Share token management API.
POST /api/share/create   - create a new share token
GET  /api/share/status   - get current share token info
POST /api/share/revoke   - revoke current share token
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Header
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ShareToken, User

_BASE_URL = os.getenv("DRAGON_BASE_URL", "http://localhost:8000")

router = APIRouter(tags=["share"])


def _require_auth(x_token: str | None, db: Session) -> User:
    """Authenticate via X-Token and return the User."""
    if not x_token:
        raise HTTPException(status_code=401, detail="Token required")
    user = db.query(User).filter(User.token == x_token).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@router.post("/api/share/create")
def create_share_token(
    speed: int = 1,
    expires_days: str | None = None,  # "7", "30", "never"
    x_token: str | None = Header(default=None),
):
    """
    Create (or replace) a share token for the authenticated crawfish.
    Returns: { "token": "...", "url": "...", "expires_at": "..." or null }
    """
    db: Session = SessionLocal()
    try:
        user = _require_auth(x_token, db)

        # Parse expiry
        expires_at = None
        if expires_days and expires_days != "never":
            days = int(expires_days)
            expires_at = datetime.now(timezone.utc) + timedelta(days=days)

        # Revoke existing share tokens for this user
        db.query(ShareToken).filter(ShareToken.crawfish_id == user.id).delete()

        # Generate new token
        token = secrets.token_urlsafe(32)
        st = ShareToken(
            crawfish_id=user.id,
            token=token,
            speed=speed,
            expires_at=expires_at,
        )
        db.add(st)
        db.commit()

        base_url = _BASE_URL
        return {
            "token": token,
            "url": f"{base_url}/world/share/{token}",
            "expires_at": expires_at.isoformat() if expires_at else None,
            "speed": speed,
        }
    finally:
        db.close()


@router.get("/api/share/status")
def get_share_status(x_token: str | None = Header(default=None)):
    """
    Get current share token info for the authenticated crawfish.
    Returns: { "has_token": bool, "token": "...", "url": "...", "expires_at": "...", "speed": int }
    """
    db: Session = SessionLocal()
    try:
        user = _require_auth(x_token, db)
        st = (
            db.query(ShareToken)
            .filter(ShareToken.crawfish_id == user.id)
            .order_by(ShareToken.created_at.desc())
            .first()
        )

        if not st:
            return {"has_token": False, "token": None, "url": None, "expires_at": None, "speed": None}

        # Check if expired
        if st.expires_at and st.expires_at < datetime.now(timezone.utc):
            return {"has_token": False, "token": None, "url": None, "expires_at": None, "speed": None}

        base_url = _BASE_URL
        return {
            "has_token": True,
            "token": st.token,
            "url": f"{base_url}/world/share/{st.token}",
            "expires_at": st.expires_at.isoformat() if st.expires_at else None,
            "speed": st.speed,
        }
    finally:
        db.close()


@router.post("/api/share/revoke")
def revoke_share_token(x_token: str | None = Header(default=None)):
    """Revoke the share token for the authenticated crawfish."""
    db: Session = SessionLocal()
    try:
        user = _require_auth(x_token, db)
        db.query(ShareToken).filter(ShareToken.crawfish_id == user.id).delete()
        db.commit()
        return {"ok": True}
    finally:
        db.close()
