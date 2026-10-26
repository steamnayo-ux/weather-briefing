"""저장소 계약 테스트 (6-1).

1부: HistoryStore 계약 - 어떤 저장소든 지켜야 할 규칙.
     지금은 SQLite만 돌리고, 6-3에서 외부 DB를 fixture에 추가하면 같은 테스트가 그대로 돈다.
2부: run_daily가 저장소를 '바꿔 끼워도' 동작하는지 (가짜 저장소 사용)
3부: send_text_to_me가 TokenStore를 통해서만 토큰을 읽고 쓰는지
"""
import time
from datetime import datetime, timedelta, timezone

import pytest

from weather_mcp import run_daily
from weather_mcp.services import history, kakao
from weather_mcp.services.store import StoreError

KST = history.KST
T0 = datetime(2026, 10, 26, 7, 0, tzinfo=KST)  # 기준 시각: 한국 시간 오전 7시
LOC = "분당구"
CH = "kakao"


# ---------------------------------------------------------------
# 1부: HistoryStore 계약
# ---------------------------------------------------------------
@pytest.fixture(params=["sqlite"])  # 6-3에서 "external"을 여기에 추가한다
def store(request, tmp_path):
    return history.SqliteHistoryStore(tmp_path / "contract.db")


def test_first_claim_is_new(store):
    record_id, reason = store.claim_send(LOC, CH, now=T0)
    assert reason == "new"
    assert record_id is not None


def test_second_claim_while_attempt_is_fresh_is_in_progress(store):
    store.claim_send(LOC, CH, now=T0)
    record_id, reason = store.claim_send(LOC, CH, now=T0 + timedelta(minutes=3))
    assert (record_id, reason) == (None, "in_progress")


def test_claim_after_sent_is_already_sent(store):
    record_id, _ = store.claim_send(LOC, CH, now=T0)
    store.finish_attempt(record_id, "sent", now=T0)
    assert store.claim_send(LOC, CH, now=T0 + timedelta(hours=1)) == (None, "already_sent")


def test_claim_after_failed_retries(store):
    first_id, _ = store.claim_send(LOC, CH, now=T0)
    store.finish_attempt(first_id, "failed", error="테스트 오류", now=T0)

    retry_id, reason = store.claim_send(LOC, CH, now=T0 + timedelta(minutes=1))
    assert reason == "retry"
    assert retry_id == first_id  # 하루 한 줄 규칙: 같은 줄을 다시 쓴다

    record = store.get_record("2026-10-26", LOC, CH)
    assert record["status"] == "attempting"
    assert record["error"] is None  # 이전 실패 메시지는 지워진다


def test_stale_attempt_is_taken_over(store):
    store.claim_send(LOC, CH, now=T0)
    _, soon = store.claim_send(LOC, CH, now=T0 + timedelta(minutes=3))
    _, later = store.claim_send(LOC, CH, now=T0 + timedelta(minutes=15))
    assert (soon, later) == ("in_progress", "retry")  # 3분 뒤는 기다림, 15분 뒤는 넘겨받음


def test_next_day_is_new(store):
    record_id, _ = store.claim_send(LOC, CH, now=T0)
    store.finish_attempt(record_id, "sent", now=T0)
    _, reason = store.claim_send(LOC, CH, now=T0 + timedelta(days=1))
    assert reason == "new"


def test_other_location_is_independent(store):
    store.claim_send(LOC, CH, now=T0)
    _, reason = store.claim_send("강남구", CH, now=T0)
    assert reason == "new"


def test_utc_time_is_converted_to_kst_date(store):
    # UTC 10/25 22:00 = 한국 10/26 07:00 (GitHub Actions cron이 도는 시각)
    utc_now = datetime(2026, 10, 25, 22, 0, tzinfo=timezone.utc)
    store.claim_send(LOC, CH, now=utc_now)
    record = store.get_record("2026-10-26", LOC, CH)
    assert record is not None
    assert record["attempted_at"].startswith("2026-10-26T07:00")


def test_finish_attempt_records_result(store):
    record_id, _ = store.claim_send(LOC, CH, now=T0)
    store.finish_attempt(record_id, "sent", now=T0 + timedelta(seconds=30))
    record = store.get_record("2026-10-26", LOC, CH)
    assert record["status"] == "sent"
    assert record["finished_at"] is not None


def test_finish_attempt_rejects_unknown_status(store):
    record_id, _ = store.claim_send(LOC, CH, now=T0)
    with pytest.raises(ValueError):
        store.finish_attempt(record_id, "done")  # 'sent'/'failed'만 허용


def test_long_error_message_is_truncated(store):
    record_id, _ = store.claim_send(LOC, CH, now=T0)
    store.finish_attempt(record_id, "failed", error="가" * 1000, now=T0)
    assert len(store.get_record("2026-10-26", LOC, CH)["error"]) <= 200


def test_force_claim_reopens_sent_record(store):
    record_id, _ = store.claim_send(LOC, CH, now=T0)
    store.finish_attempt(record_id, "sent", now=T0)
    forced_id = store.force_claim(LOC, CH, now=T0 + timedelta(hours=1))
    assert forced_id == record_id  # 같은 줄을 다시 쓴다
    assert store.get_record("2026-10-26", LOC, CH)["status"] == "attempting"


def test_force_claim_creates_record_when_missing(store):
    assert store.force_claim(LOC, CH, now=T0) is not None


def test_get_record_returns_none_when_missing(store):
    assert store.get_record("2026-10-26", LOC, CH) is None


def test_list_recent_is_newest_first_and_limited(store):
    for day in range(3):
        store.claim_send(LOC, CH, now=T0 + timedelta(days=day))
    rows = store.list_recent(limit=2)
    assert [r["send_date"] for r in rows] == ["2026-10-28", "2026-10-27"]


# ---------------------------------------------------------------
# 2부: run_daily가 저장소를 바꿔 끼워도 동작하는가
# ---------------------------------------------------------------
class FakeHistoryStore:
    """메모리에만 기록하는 가짜 저장소. run_daily가 SQLite를 모른다는 것을 확인한다."""

    def __init__(self, claim=(1, "new"), finish_error=None):
        self.claim = claim
        self.finish_error = finish_error
        self.finished = []
        self.forced = False

    def claim_send(self, location, channel, now=None):
        return self.claim

    def force_claim(self, location, channel, now=None):
        self.forced = True
        return 7

    def finish_attempt(self, record_id, status, error=None, now=None):
        if self.finish_error:
            raise self.finish_error
        self.finished.append((record_id, status, error))


def _fake_briefing(result):
    """send_briefing_to_kakao를 지정한 결과로 바꿔 주는 함수 (카카오·LLM 호출 방지)."""
    calls = []

    def fake(location, generate=None, send=None):
        calls.append(location)
        return result

    return fake, calls


def test_run_daily_records_sent_in_given_store(monkeypatch):
    fake, calls = _fake_briefing({"sent": True})
    monkeypatch.setattr(run_daily.kakao_briefing, "send_briefing_to_kakao", fake)
    fake_store = FakeHistoryStore()

    code = run_daily.main(["--location", LOC], store=fake_store)

    assert code == run_daily.EXIT_OK
    assert calls == [LOC]
    assert fake_store.finished == [(1, "sent", None)]


def test_run_daily_skips_when_already_sent(monkeypatch):
    fake, calls = _fake_briefing({"sent": True})
    monkeypatch.setattr(run_daily.kakao_briefing, "send_briefing_to_kakao", fake)
    fake_store = FakeHistoryStore(claim=(None, "already_sent"))

    code = run_daily.main(["--location", LOC], store=fake_store)

    assert code == run_daily.EXIT_OK  # 건너뜀은 실패가 아니다
    assert calls == []                # 발송 시도 자체를 하지 않는다
    assert fake_store.finished == []


def test_run_daily_records_failure_and_returns_1(monkeypatch):
    fake, _ = _fake_briefing({"sent": False, "error": "테스트 실패"})
    monkeypatch.setattr(run_daily.kakao_briefing, "send_briefing_to_kakao", fake)
    fake_store = FakeHistoryStore()

    code = run_daily.main(["--location", LOC], store=fake_store)

    assert code == run_daily.EXIT_FAILED
    assert fake_store.finished == [(1, "failed", "테스트 실패")]


def test_run_daily_force_uses_force_claim(monkeypatch):
    fake, _ = _fake_briefing({"sent": True})
    monkeypatch.setattr(run_daily.kakao_briefing, "send_briefing_to_kakao", fake)
    fake_store = FakeHistoryStore()

    run_daily.main(["--location", LOC, "--force"], store=fake_store)

    assert fake_store.forced is True
    assert fake_store.finished == [(7, "sent", None)]


def test_run_daily_keeps_result_when_recording_fails(monkeypatch, capsys):
    fake, _ = _fake_briefing({"sent": True})
    monkeypatch.setattr(run_daily.kakao_briefing, "send_briefing_to_kakao", fake)
    fake_store = FakeHistoryStore(finish_error=StoreError("이력 기록 실패: TestError"))

    code = run_daily.main(["--location", LOC], store=fake_store)

    assert code == run_daily.EXIT_OK  # 기록이 실패해도 발송 결과는 바뀌지 않는다
    assert "주의" in capsys.readouterr().out


# ---------------------------------------------------------------
# 3부: TokenStore
# ---------------------------------------------------------------
class FakeTokenStore:
    def __init__(self, tokens):
        self.tokens = tokens
        self.saved = []

    def load(self):
        return self.tokens

    def save(self, tokens):
        self.saved.append(tokens)
        self.tokens = tokens


class FakeResponse:
    status_code = 200

    def json(self):
        return {"result_code": 0}


def _fresh_tokens():
    # 만료까지 한참 남은 토큰 (갱신이 필요 없다)
    return {"access_token": "a1", "refresh_token": "r1",
            "obtained_at": int(time.time()), "expires_in": 21600}


def test_file_token_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(kakao, "TOKEN_FILE", tmp_path / "t.json")
    token_store = kakao.FileTokenStore()
    token_store.save({"access_token": "a", "refresh_token": "r"})
    assert token_store.load()["refresh_token"] == "r"


def test_send_uses_given_token_store_without_saving(monkeypatch):
    monkeypatch.setattr(kakao, "_post_message", lambda token, text: FakeResponse())
    token_store = FakeTokenStore(_fresh_tokens())

    result = kakao.send_text_to_me("테스트", store=token_store)

    assert result["ok"] is True
    assert token_store.saved == []  # 갱신이 필요 없으면 저장하지 않는다


def test_send_saves_refreshed_tokens_to_given_store(monkeypatch):
    expired = {"access_token": "old", "refresh_token": "r1", "obtained_at": 0, "expires_in": 0}
    renewed = {**_fresh_tokens(), "access_token": "new"}
    monkeypatch.setattr(kakao, "refresh_tokens", lambda tokens: renewed)
    monkeypatch.setattr(kakao, "_post_message", lambda token, text: FakeResponse())
    token_store = FakeTokenStore(expired)

    kakao.send_text_to_me("테스트", store=token_store)

    assert token_store.saved == [renewed]  # 갱신된 토큰이 지정한 저장소로 간다