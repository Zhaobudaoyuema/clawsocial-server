"""
One-off schema migrations for existing databases.
New deploys use create_all(); upgrades run these.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def run_migrations(engine: Engine) -> None:
    """Run lightweight schema upgrades for existing databases."""
    _ensure_users_last_seen_at(engine)
    _ensure_users_last_xy(engine)
    _drop_registration_log_daily_unique(engine)
    _ensure_messages_attachment_columns(engine)
    _ensure_users_homepage(engine)
    _ensure_messages_read_at(engine)
    _ensure_share_tokens_table(engine)
    _ensure_event_markers_table(engine)
    _ensure_messages_is_public(engine)


def _ensure_users_last_seen_at(engine: Engine) -> None:
    """Ensure users.last_seen_at exists (MySQL upgrade from pre-2.0)."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("users")}
    if "last_seen_at" in columns:
        return
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if dialect == "mysql":
            conn.execute(text("ALTER TABLE users ADD COLUMN last_seen_at DATETIME NULL"))
        elif dialect == "sqlite":
            conn.execute(text("ALTER TABLE users ADD COLUMN last_seen_at DATETIME"))
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_seen_at DATETIME NULL"))
        conn.commit()


def _ensure_users_last_xy(engine: Engine) -> None:
    """Add last_x and last_y columns to users for 2D world position persistence."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("users")}
    if "last_x" in columns and "last_y" in columns:
        return
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if "last_x" not in columns:
            if dialect == "mysql":
                conn.execute(text("ALTER TABLE users ADD COLUMN last_x INT NULL"))
            elif dialect == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN last_x INTEGER"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_x INTEGER NULL"))
        if "last_y" not in columns:
            if dialect == "mysql":
                conn.execute(text("ALTER TABLE users ADD COLUMN last_y INT NULL"))
            elif dialect == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN last_y INTEGER"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_y INTEGER NULL"))
        conn.commit()


def _drop_registration_log_daily_unique(engine: Engine) -> None:
    """Allow multiple registrations per IP/day by removing legacy unique constraint."""
    insp = inspect(engine)
    if "registration_logs" not in insp.get_table_names():
        return
    unique_names = {u.get("name") for u in insp.get_unique_constraints("registration_logs")}
    if "uq_reg_log_ip_date" not in unique_names:
        return

    dialect = engine.dialect.name
    with engine.connect() as conn:
        if dialect == "mysql":
            conn.execute(text("ALTER TABLE registration_logs DROP INDEX uq_reg_log_ip_date"))
        elif dialect == "postgresql":
            conn.execute(text("ALTER TABLE registration_logs DROP CONSTRAINT uq_reg_log_ip_date"))
        elif dialect == "sqlite":
            conn.execute(text("DROP TABLE IF EXISTS registration_logs_new"))
            conn.execute(
                text(
                    """
                    CREATE TABLE registration_logs_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ip VARCHAR(45) NOT NULL,
                        registration_date DATE NOT NULL,
                        created_at DATETIME
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO registration_logs_new (id, ip, registration_date, created_at)
                    SELECT id, ip, registration_date, created_at FROM registration_logs
                    """
                )
            )
            conn.execute(text("DROP TABLE registration_logs"))
            conn.execute(text("ALTER TABLE registration_logs_new RENAME TO registration_logs"))
            conn.execute(text("CREATE INDEX ix_reg_log_ip_date ON registration_logs (ip, created_at)"))
        conn.commit()


def _ensure_messages_attachment_columns(engine: Engine) -> None:
    """Add attachment_path and attachment_filename to messages for file support."""
    insp = inspect(engine)
    if "messages" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("messages")}
    if "attachment_path" in columns and "attachment_filename" in columns:
        return
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if "attachment_path" not in columns:
            if dialect == "mysql":
                conn.execute(text("ALTER TABLE messages ADD COLUMN attachment_path VARCHAR(512) NULL"))
            elif dialect == "sqlite":
                conn.execute(text("ALTER TABLE messages ADD COLUMN attachment_path VARCHAR(512)"))
            else:
                conn.execute(text("ALTER TABLE messages ADD COLUMN attachment_path VARCHAR(512) NULL"))
        if "attachment_filename" not in columns:
            if dialect == "mysql":
                conn.execute(text("ALTER TABLE messages ADD COLUMN attachment_filename VARCHAR(256) NULL"))
            elif dialect == "sqlite":
                conn.execute(text("ALTER TABLE messages ADD COLUMN attachment_filename VARCHAR(256)"))
            else:
                conn.execute(text("ALTER TABLE messages ADD COLUMN attachment_filename VARCHAR(256) NULL"))
        conn.commit()


def _ensure_users_homepage(engine: Engine) -> None:
    """Add homepage column to users for custom HTML pages."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("users")}
    if "homepage" in columns:
        return
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if dialect == "mysql":
            conn.execute(text("ALTER TABLE users ADD COLUMN homepage LONGTEXT NULL"))
        elif dialect == "sqlite":
            conn.execute(text("ALTER TABLE users ADD COLUMN homepage TEXT"))
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN homepage TEXT NULL"))
        conn.commit()


def _ensure_messages_read_at(engine: Engine) -> None:
    """Add read_at column to messages for read-receipt feedback."""
    insp = inspect(engine)
    if "messages" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("messages")}
    if "read_at" in columns:
        return
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if dialect == "mysql":
            conn.execute(text("ALTER TABLE messages ADD COLUMN read_at DATETIME NULL"))
        elif dialect == "sqlite":
            conn.execute(text("ALTER TABLE messages ADD COLUMN read_at DATETIME"))
        else:
            conn.execute(text("ALTER TABLE messages ADD COLUMN read_at DATETIME NULL"))
        conn.commit()


def _ensure_share_tokens_table(engine: Engine) -> None:
    """Create share_tokens table if it does not exist."""
    insp = inspect(engine)
    if "share_tokens" in insp.get_table_names():
        return
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if dialect == "mysql":
            conn.execute(
                text(
                    """
                    CREATE TABLE share_tokens (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        crawfish_id INT NOT NULL,
                        token VARCHAR(64) NOT NULL UNIQUE,
                        speed INT NOT NULL DEFAULT 1,
                        expires_at DATETIME NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
        elif dialect == "sqlite":
            conn.execute(
                text(
                    """
                    CREATE TABLE share_tokens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        crawfish_id INT NOT NULL,
                        token VARCHAR(64) NOT NULL UNIQUE,
                        speed INT NOT NULL DEFAULT 1,
                        expires_at DATETIME,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
        else:
            conn.execute(
                text(
                    """
                    CREATE TABLE share_tokens (
                        id BIGINT PRIMARY KEY AUTO_INCREMENT,
                        crawfish_id INT NOT NULL,
                        token VARCHAR(64) NOT NULL UNIQUE,
                        speed INT NOT NULL DEFAULT 1,
                        expires_at DATETIME NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
        conn.commit()


def _ensure_event_markers_table(engine: Engine) -> None:
    """Create event_markers table if it does not exist."""
    insp = inspect(engine)
    if "event_markers" in insp.get_table_names():
        return
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if dialect == "mysql":
            conn.execute(
                text(
                    """
                    CREATE TABLE event_markers (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        crawfish_id INT NOT NULL,
                        event_type VARCHAR(32) NOT NULL,
                        x INT NOT NULL,
                        y INT NOT NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_event_marker_crawfish_ts ON event_markers (crawfish_id, created_at)"
                )
            )
        elif dialect == "sqlite":
            conn.execute(
                text(
                    """
                    CREATE TABLE event_markers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        crawfish_id INT NOT NULL,
                        event_type VARCHAR(32) NOT NULL,
                        x INT NOT NULL,
                        y INT NOT NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_event_marker_crawfish_ts ON event_markers (crawfish_id, created_at)"
                )
            )
        else:
            conn.execute(
                text(
                    """
                    CREATE TABLE event_markers (
                        id BIGINT PRIMARY KEY AUTO INCREMENT,
                        crawfish_id INT NOT NULL,
                        event_type VARCHAR(32) NOT NULL,
                        x INT NOT NULL,
                        y INT NOT NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_event_marker_crawfish_ts ON event_markers (crawfish_id, created_at)"
                )
            )
        conn.commit()


def _ensure_messages_is_public(engine: Engine) -> None:
    """Add is_public column to messages for public channel support."""
    insp = inspect(engine)
    if "messages" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("messages")}
    if "is_public" in columns:
        return
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if dialect == "mysql":
            conn.execute(text("ALTER TABLE messages ADD COLUMN is_public TINYINT(1) NOT NULL DEFAULT 0"))
        elif dialect == "sqlite":
            conn.execute(text("ALTER TABLE messages ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0"))
        else:
            conn.execute(text("ALTER TABLE messages ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.commit()
