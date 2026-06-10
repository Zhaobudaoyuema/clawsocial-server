"""Tests for verification merge and readiness rules."""
from app.deid.discovery.standard_verify import _apply_semantic_readiness, merge_verification


def test_semantic_missed_blocks_readiness():
    readiness = _apply_semantic_readiness(
        {"ready": True, "blockers": [], "notes": []},
        {
            "scanned": True,
            "applied_count": 1,
            "missed_count": 2,
            "missed_samples": [{"category": "project_id"}],
        },
    )
    assert readiness["ready"] is False
    assert any("未落地" in b for b in readiness["blockers"])


def test_semantic_applied_sets_deep_level():
    readiness = _apply_semantic_readiness(
        {"ready": True, "blockers": [], "notes": []},
        {
            "scanned": True,
            "applied_count": 3,
            "missed_count": 0,
            "missed_samples": [],
        },
    )
    assert readiness["level"] == "deep"
    assert readiness.get("identity_safe") is True


def test_merge_verification_includes_semantic_block():
    out = merge_verification(
        {"alias_residuals": [], "metadata_clean": True},
        worker_available=False,
        semantic_block={"scanned": True, "applied_count": 0, "missed_count": 0},
    )
    assert out["semantic"]["scanned"] is True


def test_semantic_skipped_not_export_ready():
    out = merge_verification(
        {"alias_residuals": [], "metadata_clean": True},
        worker_available=True,
        finish_verify_mode="program_only",
        semantic_block={"scanned": False, "applied_count": 0, "missed_count": 0},
    )
    assert out["readiness"]["ready"] is False
    assert "可外发" not in out["summary"]
    assert out["passed"] is False
    assert out["worker_available"] is True


def test_deep_completed_can_export():
    out = merge_verification(
        {"alias_residuals": [], "metadata_clean": True},
        worker_available=True,
        finish_verify_mode="program_only",
        deep_completed=True,
        semantic_block={"scanned": True, "applied_count": 2, "missed_count": 0, "selected_count": 2},
    )
    assert out["readiness"]["ready"] is True
    assert "可外发" in out["summary"]
