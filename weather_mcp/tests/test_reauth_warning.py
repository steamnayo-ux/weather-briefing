"""재인증 임박 경고 테스트. 시간은 NOW로 고정하고, 실제 카카오·DB는 쓰지 않는다."""
from datetime import datetime

from weather_mcp import run_daily
from weather_mcp.services import history

NOW = datetime(2026, 12, 10, 7, 0, tzinfo=history.KST)
TTL = 5184000  # 60일(초)


class FakeTokenStore:
    def __init__(self, tokens):
        self.tokens = tokens

    def load(self):
        return self.tokens


def tokens_expiring_in(days):
    """NOW 기준으로 refresh가 days일 뒤 만료되는 토큰."""
    return {
        "refresh_token_obtained_at": NOW.timestamp() + days * 86400 - TTL,
        "refresh_token_expires_in": TTL,
    }


def make(tmp_path, tokens):
    return history.SqliteHistoryStore(tmp_path / "t.db"), FakeTokenStore(tokens)


def test_far_from_expiry_sends_nothing(tmp_path):
    store, tokens = make(tmp_path, tokens_expiring_in(40))
    sent = []
    run_daily._warn_reauth("분당구", store, tokens, sent.append, NOW)
    assert sent == []


def test_near_expiry_warns_once_per_day(tmp_path):
    store, tokens = make(tmp_path, tokens_expiring_in(10))
    sent = []
    run_daily._warn_reauth("분당구", store, tokens, sent.append, NOW)
    run_daily._warn_reauth("분당구", store, tokens, sent.append, NOW)  # 같은 날 두 번째
    assert len(sent) == 1
    assert "재인증" in sent[0]


def test_unknown_issue_time_sends_nothing(tmp_path):
    store, tokens = make(tmp_path, {})  # 발급 시각 기록 없음 → days는 None
    sent = []
    run_daily._warn_reauth("분당구", store, tokens, sent.append, NOW)
    assert sent == []


def test_failed_warning_is_retried_and_never_raises(tmp_path):
    store, tokens = make(tmp_path, tokens_expiring_in(5))
    calls = []

    def broken(text):
        calls.append(text)
        raise RuntimeError("발송 실패")

    run_daily._warn_reauth("분당구", store, tokens, broken, NOW)  # 예외가 밖으로 나오면 안 됨
    run_daily._warn_reauth("분당구", store, tokens, broken, NOW)  # failed라서 다시 시도
    assert len(calls) == 2


def test_main_warns_after_successful_briefing(tmp_path, monkeypatch):
    monkeypatch.setattr(run_daily.kakao_briefing, "send_briefing_to_kakao",
                        lambda location, generate=None, send=None: {"sent": True})
    store, tokens = make(tmp_path, tokens_expiring_in(3))
    sent = []
    code = run_daily.main(["--location", "분당구"], send=sent.append, now=NOW,
                          store=store, token_store=tokens)
    assert code == run_daily.EXIT_OK
    assert len(sent) == 1 and "재인증" in sent[0]  # 브리핑은 가짜라 카톡은 경고 1건뿐


def test_main_does_not_warn_when_briefing_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(run_daily.kakao_briefing, "send_briefing_to_kakao",
                        lambda location, generate=None, send=None: {"sent": False, "error": "x"})
    store, tokens = make(tmp_path, tokens_expiring_in(3))
    sent = []
    code = run_daily.main(["--location", "분당구"], send=sent.append, now=NOW,
                          store=store, token_store=tokens)
    assert code == run_daily.EXIT_FAILED
    assert sent == []