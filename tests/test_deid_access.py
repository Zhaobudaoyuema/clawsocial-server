"""Deid daily access token (server-side only)."""
from datetime import date

from app.deid.access_token import (
    _EPOCH,
    current_deid_day_token,
    issue_deid_access_session,
    validate_deid_access_session,
    validate_deid_day_code,
)


def test_day_code_is_days_since_epoch(monkeypatch):
    monkeypatch.setattr(
        "app.deid.access_token.beijing_today",
        lambda: date(2023, 6, 8),
    )
    assert current_deid_day_token() == 0
    assert validate_deid_day_code("0")
    assert not validate_deid_day_code("1")


def test_day_code_advances_daily(monkeypatch):
    monkeypatch.setattr(
        "app.deid.access_token.beijing_today",
        lambda: date(2023, 6, 10),
    )
    assert current_deid_day_token() == 2
    assert validate_deid_day_code(2)
    assert not validate_deid_day_code(1)


def test_session_is_opaque_and_server_validated(monkeypatch):
    monkeypatch.setattr(
        "app.deid.access_token.beijing_today",
        lambda: date(2023, 6, 10),
    )
    session = issue_deid_access_session()
    assert validate_deid_access_session(session)
    assert not validate_deid_access_session("1098")
    assert not validate_deid_access_session(session + "x")
    monkeypatch.setattr(
        "app.deid.access_token.beijing_today",
        lambda: date(2023, 6, 11),
    )
    assert not validate_deid_access_session(session)


def test_epoch_is_2023_06_08():
    assert _EPOCH == date(2023, 6, 8)
