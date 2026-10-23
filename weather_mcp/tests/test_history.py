"""history.py 테스트. 모든 테스트는 임시 폴더의 DB를 쓴다 (실제 data/weather.db는 건드리지 않는다)."""
from datetime import datetime

import pytest

from weather_mcp.services import history
from weather_mcp.services.history import KST

NOW = datetime(2026, 10, 24, 7, 0, 5, tzinfo=KST)


def test_add_attempt_creates_attempting_row(tmp_path):
    db = tmp_path / "t.db"
    record_id = history.add_attempt("분당구", "kakao", db_path=db, now=NOW)
    row = history.get_record("2026-10-24", "분당구", "kakao", db_path=db)

    assert record_id is not None
    assert row["status"] == "attempting"
    assert row["attempted_at"] == "2026-10-24T07:00:05+09:00"
    assert row["finished_at"] is None


def test_same_day_duplicate_returns_none(tmp_path):
    db = tmp_path / "t.db"
    first = history.add_attempt("분당구", "kakao", db_path=db, now=NOW)
    second = history.add_attempt("분당구", "kakao", db_path=db, now=NOW)

    assert first is not None
    assert second is None                              # DB가 중복을 막았다
    assert len(history.list_recent(db_path=db)) == 1   # 기록은 한 줄뿐


def test_other_day_location_or_channel_is_allowed(tmp_path):
    db = tmp_path / "t.db"
    tomorrow = datetime(2026, 10, 25, 7, 0, 0, tzinfo=KST)

    assert history.add_attempt("분당구", "kakao", db_path=db, now=NOW) is not None
    assert history.add_attempt("분당구", "kakao", db_path=db, now=tomorrow) is not None  # 다른 날
    assert history.add_attempt("강남구", "kakao", db_path=db, now=NOW) is not None       # 다른 지역
    assert history.add_attempt("분당구", "email", db_path=db, now=NOW) is not None       # 다른 채널


def test_finish_sent(tmp_path):
    db = tmp_path / "t.db"
    record_id = history.add_attempt("분당구", "kakao", db_path=db, now=NOW)
    later = datetime(2026, 10, 24, 7, 0, 9, tzinfo=KST)
    history.finish_attempt(record_id, "sent", db_path=db, now=later)
    row = history.get_record("2026-10-24", "분당구", "kakao", db_path=db)

    assert row["status"] == "sent"
    assert row["finished_at"] == "2026-10-24T07:00:09+09:00"
    assert row["error"] is None


def test_finish_failed_keeps_short_error(tmp_path):
    db = tmp_path / "t.db"
    record_id = history.add_attempt("분당구", "kakao", db_path=db, now=NOW)
    history.finish_attempt(record_id, "failed", error="x" * 500, db_path=db, now=NOW)
    row = history.get_record("2026-10-24", "분당구", "kakao", db_path=db)

    assert row["status"] == "failed"
    assert len(row["error"]) == history.ERROR_MAX      # 긴 메시지는 잘라서 저장한다


def test_finish_rejects_invalid_status(tmp_path):
    db = tmp_path / "t.db"
    record_id = history.add_attempt("분당구", "kakao", db_path=db, now=NOW)
    with pytest.raises(ValueError):
        history.finish_attempt(record_id, "attempting", db_path=db)


def test_get_record_missing_returns_none(tmp_path):
    assert history.get_record("2026-10-24", "분당구", "kakao", db_path=tmp_path / "t.db") is None


def test_creates_missing_folder(tmp_path):
    db = tmp_path / "새폴더" / "t.db"
    history.add_attempt("분당구", "kakao", db_path=db, now=NOW)
    assert db.exists()


def test_default_db_lives_in_data_folder():
    # 기본 경로가 .gitignore가 막는 data 폴더인지 확인한다
    assert history.DB_PATH.parent.name == "data"
    assert history.DB_PATH.name == "weather.db"