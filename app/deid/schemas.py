"""Pydantic schemas for deid REST API."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PackOut(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    is_default: bool
    is_active: bool

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: int
    status: str
    pack_ids: list[int] = []
    original_filename: str
    engine: str | None = None
    verification: dict[str, Any] | None = None
    run_summary: dict[str, Any] | None = None
    override_reason: str | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    hours_until_cleanup: float | None = None


class JobEntityOut(BaseModel):
    id: int
    canonical_name: str
    entity_type: str
    source: str
    placeholder: str | None
    is_excluded: bool
    hit_count: int
    aliases: list[str] = []


class ManualEntityIn(BaseModel):
    canonical_name: str
    entity_type: str = "company"
    aliases: list[str] = Field(default_factory=list)
    save_to_library: bool = True


class EntityPatchIn(BaseModel):
    is_excluded: bool | None = None
    placeholder: str | None = None


class ConfirmIn(BaseModel):
    preview_ack: bool = True
    entity_ids: list[int] | None = None
    remember_ids: list[int] | None = None


class RunIn(BaseModel):
    entity_ids: list[int] | None = None
    remember_ids: list[int] | None = None


class RunOut(BaseModel):
    job_id: int
    status: str
    engine: str | None
    verification: dict[str, Any] | None
    run_summary: dict[str, Any] | None


class ExportQuery(BaseModel):
    override_ack: bool = False
    override_reason: str | None = None


class LibraryEntityIn(BaseModel):
    pack_id: int
    canonical_name: str
    entity_type: str = "company"
    placeholder_prefix: str = "公司"
    aliases: list[str] = Field(default_factory=list)
    notes: str | None = None


class LibraryEntityPatch(BaseModel):
    canonical_name: str | None = None
    entity_type: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class AliasIn(BaseModel):
    alias_text: str


class PatternRuleIn(BaseModel):
    name: str
    regex_pattern: str
    entity_type: str = "custom"
    placeholder_prefix: str = "实体"
    pack_id: int | None = None
    priority: int = 0


class PatternTestIn(BaseModel):
    regex_pattern: str
    sample_text: str


class ScanPromptIn(BaseModel):
    prompt: str = Field(..., min_length=1)


class WhitelistIn(BaseModel):
    term: str
    term_type: str = "exact"
    category: str | None = None
    pack_id: int | None = None


class EntityTypeIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    label: str = Field(..., min_length=1, max_length=64)
    placeholder_prefix: str = Field(..., min_length=1, max_length=32)


class EntityTypePatch(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=64)
    placeholder_prefix: str | None = Field(None, min_length=1, max_length=32)


class MergeEntitiesIn(BaseModel):
    target_entity_id: int
    source_entity_ids: list[int]


class RehydrateIn(BaseModel):
    text: str = Field(..., min_length=1)


class RehydrateOut(BaseModel):
    text: str
    resolved: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
