"""services/kakao.py 테스트. 실제 카카오 API는 호출하지 않는다."""
import json
import time

import pytest

from weather_mcp.services import kakao


class FakeResponse:
    """httpx 응답 흉내: status_code와 json()만 제공한다."""

    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}

    def json(self):
        return self._body


def ok():
    return FakeResponse(200, {"result_code": 0})


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    """임시 토큰 파일과 가짜 환경변수 준비 (진짜 kakao_tokens.json은 건드리지 않음)."""
    path = tmp_path / "kakao_tokens.json"
    monkeypatch.setattr(kakao, "TOKEN_FILE", path)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    monkeypatch.delenv("KAKAO_CLIENT_SECRET", raising=False)
    return path


def write_tokens(path, **overrides):
    tokens = {
        "access_token": "old-access",
        "refresh_token": "old-refresh",
        "expires_in": 21599,
        "obtained_at": int(time.time()),
    }
    tokens.update(overrides)
    path.write_text(json.dumps(tokens), encoding="utf-8")


def install_fake_post(monkeypatch, responses):
    """URL별로 준비한 응답을 순서대로 돌려주고, 호출 기록(calls)을 반환한다.
    준비하지 않은 URL을 호출하면 KeyError로 테스트가 실패한다."""
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return responses[url].pop(0)

    monkeypatch.setattr(kakao.httpx, "post", fake_post)
    return calls


def test_is_expiring():
    now = 1_000_000
    fresh = {"obtained_at": now, "expires_in": 21599}
    assert kakao.is_expiring(fresh, now=now) is False
    assert kakao.is_expiring(fresh, now=now + 21599 - 100) is True  # 만료 5분 이내
    assert kakao.is_expiring(fresh, now=now + 30000) is True  # 이미 만료
    assert kakao.is_expiring({}, now=now) is True  # obtained_at 없으면 갱신


def test_valid_token_sends_without_refresh(token_file, monkeypatch):
    write_tokens(token_file)
    calls = install_fake_post(monkeypatch, {kakao.SEND_URL: [ok()]})

    result = kakao.send_text_to_me("테스트")

    assert result["ok"] is True
    assert [url for url, _ in calls] == [kakao.SEND_URL]  # 갱신 호출 없음
    assert calls[0][1]["headers"]["Authorization"] == "Bearer old-access"


def test_expiring_token_is_refreshed_before_send(token_file, monkeypatch):
    write_tokens(token_file, obtained_at=int(time.time()) - 30000)
    calls = install_fake_post(monkeypatch, {
        kakao.TOKEN_URL: [FakeResponse(200, {"access_token": "new-access", "expires_in": 21599})],
        kakao.SEND_URL: [ok()],
    })

    kakao.send_text_to_me("테스트")

    assert [url for url, _ in calls] == [kakao.TOKEN_URL, kakao.SEND_URL]
    refresh_data = calls[0][1]["data"]
    assert refresh_data["grant_type"] == "refresh_token"
    assert refresh_data["client_id"] == "test-key"
    assert "client_secret" not in refresh_data  # 시크릿 환경변수가 없으면 보내지 않음
    assert calls[1][1]["headers"]["Authorization"] == "Bearer new-access"
    saved = json.loads(token_file.read_text(encoding="utf-8"))
    assert saved["access_token"] == "new-access"
    assert saved["refresh_token"] == "old-refresh"  # 새 refresh가 없으면 기존 값 유지


def test_new_refresh_token_replaces_old(token_file, monkeypatch):
    write_tokens(token_file, obtained_at=int(time.time()) - 30000)
    install_fake_post(monkeypatch, {
        kakao.TOKEN_URL: [FakeResponse(200, {
            "access_token": "new-access", "expires_in": 21599,
            "refresh_token": "new-refresh",
        })],
        kakao.SEND_URL: [ok()],
    })

    kakao.send_text_to_me("테스트")

    saved = json.loads(token_file.read_text(encoding="utf-8"))
    assert saved["refresh_token"] == "new-refresh"


def test_401_triggers_refresh_and_one_retry(token_file, monkeypatch):
    write_tokens(token_file)  # 만료 전처럼 보이지만 서버가 401을 주는 경우
    calls = install_fake_post(monkeypatch, {
        kakao.SEND_URL: [FakeResponse(401, {"code": -401, "msg": "expired"}), ok()],
        kakao.TOKEN_URL: [FakeResponse(200, {"access_token": "new-access", "expires_in": 21599})],
    })

    result = kakao.send_text_to_me("테스트")

    assert result["ok"] is True
    assert [url for url, _ in calls] == [kakao.SEND_URL, kakao.TOKEN_URL, kakao.SEND_URL]
    assert calls[2][1]["headers"]["Authorization"] == "Bearer new-access"


def test_401_twice_raises_without_endless_retry(token_file, monkeypatch):
    write_tokens(token_file)
    calls = install_fake_post(monkeypatch, {
        kakao.SEND_URL: [FakeResponse(401, {"code": -401}), FakeResponse(401, {"code": -401})],
        kakao.TOKEN_URL: [FakeResponse(200, {"access_token": "new-access", "expires_in": 21599})],
    })

    with pytest.raises(kakao.KakaoError):
        kakao.send_text_to_me("테스트")

    assert len(calls) == 3  # 발송 → 갱신 → 발송, 그 이후 재시도 없음


def test_refresh_failure_message_has_no_secrets(token_file, monkeypatch):
    write_tokens(token_file, obtained_at=int(time.time()) - 30000)
    install_fake_post(monkeypatch, {
        kakao.TOKEN_URL: [FakeResponse(400, {"error": "invalid_grant", "error_code": "KOE320"})],
    })

    with pytest.raises(kakao.KakaoError) as exc:
        kakao.send_text_to_me("테스트")

    message = str(exc.value)
    assert "KOE320" in message
    assert "old-refresh" not in message
    assert "test-key" not in message


@pytest.mark.parametrize("text", ["", "   ", "가" * (kakao.MAX_TEXT_LEN + 1)])
def test_invalid_text_is_rejected_without_calling_api(token_file, monkeypatch, text):
    write_tokens(token_file)
    calls = install_fake_post(monkeypatch, {})

    with pytest.raises(kakao.KakaoError):
        kakao.send_text_to_me(text)

    assert calls == []


def test_missing_token_file_raises(token_file):
    # token_file 경로에 파일을 만들지 않았으므로 없는 상태
    with pytest.raises(kakao.KakaoError):
        kakao.load_tokens()