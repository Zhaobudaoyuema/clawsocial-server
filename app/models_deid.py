"""SQLAlchemy models for financial document de-identification (deid)."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.time_utils import now_beijing


def _now() -> datetime:
    return now_beijing()


class DeidClientPack(Base):
    __tablename__ = "deid_client_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DeidEntity(Base):
    __tablename__ = "deid_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pack_id: Mapped[int] = mapped_column(Integer, ForeignKey("deid_client_packs.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # company / person / org / custom
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    placeholder_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="seed", nullable=False)
    times_hit_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class DeidEntityAlias(Base):
    __tablename__ = "deid_entity_aliases"
    __table_args__ = (UniqueConstraint("entity_id", "alias_text", name="uq_deid_entity_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[int] = mapped_column(Integer, ForeignKey("deid_entities.id"), nullable=False, index=True)
    alias_text: Mapped[str] = mapped_column(String(500), nullable=False)
    match_mode: Mapped[str] = mapped_column(String(16), default="exact", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    times_hit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_from: Mapped[str] = mapped_column(String(32), default="seed", nullable=False)


class DeidPatternRule(Base):
    __tablename__ = "deid_pattern_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pack_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("deid_client_packs.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    regex_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    placeholder_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DeidWhitelistTerm(Base):
    __tablename__ = "deid_whitelist_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pack_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("deid_client_packs.id"), nullable=True, index=True)
    term: Mapped[str] = mapped_column(String(500), nullable=False)
    term_type: Mapped[str] = mapped_column(String(16), default="exact", nullable=False)  # exact / regex
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DeidSetting(Base):
    __tablename__ = "deid_settings"

    key: Mapped[str] = mapped_column("key", String(64), primary_key=True, quote=True)
    value: Mapped[str] = mapped_column("value", Text, nullable=False, quote=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DeidJob(Base):
    __tablename__ = "deid_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    pack_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), default="docx", nullable=False)
    stored_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_ack_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    run_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    files_purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    prompt_extra: Mapped[str | None] = mapped_column(Text, nullable=True)
    use_worker: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    progress_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    scan_entities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    deep_risks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    deep_pairs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_lines_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_selection_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_entity_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    gaps_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflect_round_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    semantic_skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    initial_entities_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_re_run_delta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    re_run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    experience_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DeidGlobalExperience(Base):
    __tablename__ = "deid_global_experience"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(String(100), nullable=False)
    source_job_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("deid_jobs.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DeidJobEntity(Base):
    __tablename__ = "deid_job_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("deid_jobs.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    placeholder: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="preset", nullable=False)  # preset / manual
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_merged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    library_entity_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("deid_entities.id"), nullable=True)
    save_to_library: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DeidJobEntityAlias(Base):
    __tablename__ = "deid_job_entity_aliases"
    __table_args__ = (UniqueConstraint("job_entity_id", "alias_text", name="uq_deid_job_entity_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_entity_id: Mapped[int] = mapped_column(Integer, ForeignKey("deid_job_entities.id"), nullable=False, index=True)
    alias_text: Mapped[str] = mapped_column(String(500), nullable=False)


class DeidEntityMapping(Base):
    __tablename__ = "deid_entity_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("deid_jobs.id"), nullable=False, index=True)
    original_text: Mapped[str] = mapped_column(String(500), nullable=False)
    placeholder: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class DeidWorkerCall(Base):
    """Audit log: one Mac Worker chat-completions request per row."""

    __tablename__ = "deid_worker_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deid_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flow_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    chunk_total: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    response_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parsed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


class DeidHitLog(Base):
    __tablename__ = "deid_hit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("deid_jobs.id"), nullable=False, index=True)
    file_part: Mapped[str] = mapped_column(String(128), nullable=False)
    paragraph_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
