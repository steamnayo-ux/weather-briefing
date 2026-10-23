"""run_daily.py 테스트. 발송·AI 호출은 모두 가짜로 바꾸고, 이력은 임시 DB에 남긴다."""
from datetime import datetime

import pytest

from weather_mcp import run_daily
from weather_mcp.services import ai_briefing, history, kakao
from weather_mcp.services.history import KST

NOW = datetime(2026, 10, 24, 7, 0, 5, tzinfo=KST)
TODAY = "2026-10-24"
TEXT = "맑고 20°C입니다."


@pytest.fixture(autouse=True)
def block_real_calls(monkeypatch):
    """실수로 진짜 카톡 발송이나 AI 호출이 일어나지 않게 막는다."""
    def forbidden(*args, **kwargs):
        raise AssertionError("테스트에서 실제 호출이 일어났습니다")

    monkeypatch.setattr(kakao, "send_text_to_me", forbidden)
    monkeypatch.setattr(ai_briefing, "generate_briefing", forbidden)


def make_generate(result=None):
    """가짜 브리핑 생성 함수."""
    def fake(name, max_chars=None):
        if result is not None:
            return result
        return {"location": name, "briefing": TEXT, "model": "fake",
                "generated_at": "t", "warnings": []}
    return fake


def make_send(error=None):
    """가짜 카톡 발송 함수. 보낸 문장을 send.sent에 모은다."""
    def fake(text):
        if error is not None:
            raise error
        fake.sent.append(text)
    fake.sent = []
    return fake


def run(args, db, send, generate=None):
    return run_daily.main(args, send=send, generate=generate or make_generate(),
                          db_path=db, now=NOW)


def record(db, location="분당구"):
    return history.get_record(TODAY, location, "kakao", db_path=db)


def test_no_location_returns_usage_error(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("DAILY_LOCATION", raising=False)
    send = make_send()
    code = run([], tmp_path / "t.db", send)

    assert code == run_daily.EXIT_USAGE
    assert send.sent == []
    assert "DAILY_LOCATION" in capsys.readouterr().out


def test_env_location_is_used(monkeypatch, tmp_path):
    monkeypatch.setenv("DAILY_LOCATION", "분당구")
    db = tmp_path / "t.db"
    send = make_send()
    code = run([], db, send)

    assert code == 0
    assert send.sent == [TEXT]
    assert record(db)["status"] == "sent"


def test_cli_location_overrides_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DAILY_LOCATION", "분당구")
    db = tmp_path / "t.db"
    run(["--location", "강남구"], db, make_send())

    assert record(db, "강남구") is not None
    assert record(db, "분당구") is None


def test_second_run_same_day_is_skipped(tmp_path, capsys):
    db = tmp_path / "t.db"
    send = make_send()
    first = run(["--location", "분당구"], db, send)
    second = run(["--location", "분당구"], db, send)

    assert first == 0 and second == 0      # 건너뜀은 실패가 아니다
    assert len(send.sent) == 1             # 한 번만 보냈다
    assert "이미 발송" in capsys.readouterr().out


def test_data_error_is_recorded_as_failed(tmp_path):
    db = tmp_path / "t.db"
    send = make_send()
    generate = make_generate({"error": "날씨와 대기질 정보를 모두 가져오지 못했습니다", "warnings": []})
    code = run(["--location", "분당구"], db, send, generate)

    assert code == run_daily.EXIT_FAILED
    assert send.sent == []                 # 오류 브리핑은 발송하지 않는다
    assert record(db)["status"] == "failed"
    assert "모두 가져오지" in record(db)["error"]


def test_failed_run_can_be_retried(tmp_path):
    db = tmp_path / "t.db"
    send = make_send()
    bad = make_generate({"error": "일시 오류", "warnings": []})

    assert run(["--location", "분당구"], db, send, bad) == 1
    assert run(["--location", "분당구"], db, send) == 0   # 같은 날 재시도 허용

    assert send.sent == [TEXT]
    assert record(db)["status"] == "sent"
    assert record(db)["error"] is None


def test_dry_run_sends_and_records_nothing(tmp_path, capsys):
    db = tmp_path / "t.db"
    send = make_send()
    code = run(["--location", "분당구", "--dry-run"], db, send)

    assert code == 0
    assert send.sent == []
    assert history.list_recent(db_path=db) == []
    assert TEXT in capsys.readouterr().out


def test_force_resends_after_sent(tmp_path):
    db = tmp_path / "t.db"
    send = make_send()
    run(["--location", "분당구"], db, send)
    code = run(["--location", "분당구", "--force"], db, send)

    assert code == 0
    assert len(send.sent) == 2
    assert record(db)["status"] == "sent"


def test_kakao_error_is_recorded_as_failed(tmp_path):
    db = tmp_path / "t.db"
    send = make_send(error=kakao.KakaoError("토큰이 만료되었습니다"))
    code = run(["--location", "분당구"], db, send)

    assert code == run_daily.EXIT_FAILED
    assert record(db)["status"] == "failed"
    assert "토큰이 만료" in record(db)["error"]


def test_unexpected_exception_does_not_leak(tmp_path, capsys):
    db = tmp_path / "t.db"
    send = make_send(error=RuntimeError("secret-key-123"))
    code = run(["--location", "분당구"], db, send)

    assert code == run_daily.EXIT_FAILED
    assert "secret-key-123" not in str(record(db))
    assert "secret-key-123" not in capsys.readouterr().out