"""history.force_claim 테스트 (수동 재발송). 임시 DB만 쓴다."""
from datetime import datetime, timedelta

from weather_mcp.services import history
from weather_mcp.services.history import KST

NOW = datetime(2026, 10, 24, 7, 0, 5, tzinfo=KST)


def test_force_claim_without_record_creates_one(tmp_path):
    db = tmp_path / "t.db"
    record_id = history.force_claim("분당구", "kakao", db_path=db, now=NOW)
    row = history.get_record("2026-10-24", "분당구", "kakao", db_path=db)

    assert record_id is not None
    assert row["status"] == "attempting"


def test_force_claim_after_sent_takes_it_again(tmp_path):
    db = tmp_path / "t.db"
    first_id, _ = history.claim_send("분당구", "kakao", db_path=db, now=NOW)
    history.finish_attempt(first_id, "sent", db_path=db, now=NOW)
    record_id = history.force_claim("분당구", "kakao", db_path=db, now=NOW + timedelta(hours=1))
    row = history.get_record("2026-10-24", "분당구", "kakao", db_path=db)

    assert record_id == first_id                      # 같은 줄을 다시 쓴다 (하루 한 줄 규칙 유지)
    assert row["status"] == "attempting"
    assert row["finished_at"] is None
    assert row["attempted_at"] == "2026-10-24T08:00:05+09:00"


def test_force_claim_even_when_in_progress(tmp_path):
    db = tmp_path / "t.db"
    first_id, _ = history.claim_send("분당구", "kakao", db_path=db, now=NOW)
    record_id = history.force_claim("분당구", "kakao", db_path=db, now=NOW + timedelta(minutes=1))

    assert record_id == first_id