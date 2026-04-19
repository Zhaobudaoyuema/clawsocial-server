"""
Shared authentication helpers for ClawSocial.

Provides token-to-User resolution used by both REST handlers and WS handlers.
"""
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.time_utils import now_beijing


def get_current_user(token: str, db: Session | None = None) -> User:
    """
    Resolve a token to a User, updating last_seen_at.
    Raises ValueError if token is invalid.

    Args:
        token: The user's token.
        db: Optional injected session. When provided (e.g. from FastAPI Depends),
            the test override is respected. When None (e.g. WS handlers), a
            fresh session is created internally.
    """
    own_db = False
    if db is None:
        db_gen = get_db()
        db = next(db_gen)
        own_db = True
    try:
        user = db.query(User).filter(User.token == token).first()
        if not user:
            raise ValueError("Token 无效")
        user.last_seen_at = now_beijing()
        db.commit()
        db.refresh(user)
        return user
    finally:
        if own_db:
            db.close()
