import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

# When TESTING=1, skip MySQL engine creation — tests provide their own
# in-memory SQLite via dependency override, so this engine is never used.
if os.getenv("TESTING") == "1":
    # Placeholder: never actually used in test mode (get_db is overridden in conftest.py)
    DATABASE_URL = "sqlite:///:memory:"
    _engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_USER = os.getenv("DB_USER", "relay")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "relaypass")
    DB_NAME = os.getenv("DB_NAME", "clawsocial")

    # quote_plus avoids @ / # / : in passwords breaking the connection URL
    # charset=utf8mb4 for proper multi-byte character storage
    DATABASE_URL = (
        f"mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    _engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=50,
        max_overflow=30,
    )

# Expose engine and SessionLocal so other modules can import them
engine = _engine
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
