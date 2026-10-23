"""history.claim_send 테스트 (중복 방지). 임시 DB만 쓴다."""
from datetime import datetime, timedelta, timezone

from weather_mcp.services import history
from weather_mcp.services.history import KST

NOW = datetime(2026, 10, 24, 7, 0, 5, tzinfo=KST)


def test_first_claim_is_new(tmp_path):
    db = tmp_path / "t.db"
    record_id, reason = history.claim_send("분당구", "kakao", db_path=db, now=NOW)

    assert record_id is not None
    assert reason == "new"


def test_second_claim_while_attempt_is_fresh_is_in_progress(tmp_path):
    db = tmp_path / "t.db"
    history.claim_send("분당구", "kakao", db_path=db, now=NOW)
    record_id, reason = history.claim_send(
        "분당구", "kakao", db_path=db, now=NOW + timedelta(minutes=9))  # 10분 안

    assert record_id is None
    assert reason == "in_progress"


def test_claim_after_sent_is_already_sent(tmp_path):
    db = tmp_path / "t.db"
    first_id, _ = history.claim_send("분당구", "kakao", db_path=db, now=NOW)
    history.finish_attempt(first_id, "sent", db_path=db, now=NOW)
    record_id, reason = history.claim_send(
        "분당구", "kakao", db_path=db, now=NOW + timedelta(hours=1))

    assert record_id is None
    assert reason == "already_sent"   # 성공한 날은 몇 시간이 지나도 다시 보내지 않는다


def test_claim_after_failed_retries(tmp_path):
    db = tmp_path / "t.db"
    first_id, _ = history.claim_send("분당구", "kakao", db_path=db, now=NOW)
    history.finish_attempt(first_id, "failed", error="에어코리아 HTTP 504", db_path=db, now=NOW)
    retry_time = NOW + timedelta(minutes=1)
    record_id, reason = history.claim_send("분당구", "kakao", db_path=db, now=retry_time)
    row = history.get_record("2026-10-24", "분당구", "kakao", db_path=db)

    assert record_id == first_id and reason == "retry"
    assert row["status"] == "attempting"
    assert row["finished_at"] is None and row["error"] is None   # 이전 실패 흔적은 지운다
    assert row["attempted_at"] == "2026-10-24T07:01:05+09:00"


def test_stale_attempt_is_taken_over(tmp_path):
    db = tmp_path / "t.db"
    history.claim_send("분당구", "kakao", db_path=db, now=NOW)   # 시도 중 상태로 멈췄다고 가정
    record_id, reason = history.claim_send(
        "분당구", "kakao", db_path=db, now=NOW + timedelta(minutes=11))  # 10분 초과

    assert record_id is not None
    assert reason == "retry"


def test_next_day_is_new(tmp_path):
    db = tmp_path / "t.db"
    first_id, _ = history.claim_send("분당구", "kakao", db_path=db, now=NOW)
    history.finish_attempt(first_id, "sent", db_path=db, now=NOW)
    record_id, reason = history.claim_send(
        "분당구", "kakao", db_path=db, now=NOW + timedelta(days=1))

    assert record_id is not None
    assert reason == "new"


def test_other_location_is_independent(tmp_path):
    db = tmp_path / "t.db"
    history.claim_send("분당구", "kakao", db_path=db, now=NOW)
    record_id, reason = history.claim_send("강남구", "kakao", db_path=db, now=NOW)

    assert record_id is not None
    assert reason == "new"


def test_utc_time_is_converted_to_kst_date(tmp_path):
    # UTC 22:00은 한국 시간으로 다음 날 07:00이다. 서버가 UTC여도 한국 날짜로 기록해야 한다
    db = tmp_path / "t.db"
    utc_now = datetime(2026, 10, 23, 22, 0, 0, tzinfo=timezone.utc)
    history.claim_send("분당구", "kakao", db_path=db, now=utc_now)
    row = history.get_record("2026-10-24", "분당구", "kakao", db_path=db)

    assert row is not None
    assert row["attempted_at"] == "2026-10-24T07:00:00+09:00"