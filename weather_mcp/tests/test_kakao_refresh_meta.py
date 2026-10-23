"""kakao.py의 refresh 토큰 관리(5-4) 테스트. 토큰 파일은 임시 폴더에, HTTP는 가짜로 바꾼다."""
import json

import pytest

from weather_mcp.services import kakao

DAY = 86400


class FakeResp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def kakao_env(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")
    monkeypatch.delenv("KAKAO_CLIENT_SECRET", raising=False)


def fake_post(response):
    return lambda *args, **kwargs: response


def test_save_tokens_leaves_no_temp_file(tmp_path, monkeypatch):
    token_file = tmp_path / "kakao_tokens.json"
    monkeypatch.setattr(kakao, "TOKEN_FILE", token_file)
    kakao.save_tokens({"access_token": "a", "refresh_token": "r"})

    assert json.loads(token_file.read_text(encoding="utf-8"))["refresh_token"] == "r"
    assert [p.name for p in tmp_path.iterdir()] == ["kakao_tokens.json"]   # 임시 파일이 남지 않는다


def test_failed_replace_keeps_old_file(tmp_path, monkeypatch):
    token_file = tmp_path / "kakao_tokens.json"
    token_file.write_text(json.dumps({"refresh_token": "old"}), encoding="utf-8")
    monkeypatch.setattr(kakao, "TOKEN_FILE", token_file)

    def boom(src, dst):
        raise OSError("disk problem")

    monkeypatch.setattr(kakao.os, "replace", boom)
    with pytest.raises(OSError):
        kakao.save_tokens({"refresh_token": "new"})

    # 바꿔치기가 실패해도 기존 파일은 그대로다
    assert json.loads(token_file.read_text(encoding="utf-8"))["refresh_token"] == "old"


def test_refresh_days_left():
    tokens = {"refresh_token_obtained_at": 1000, "refresh_token_expires_in": 60 * DAY}
    assert kakao.refresh_days_left(tokens, now=1000 + 10 * DAY) == pytest.approx(50.0)


def test_refresh_days_left_unknown_without_issue_time():
    assert kakao.refresh_days_left({"refresh_token": "r"}) is None


def test_new_refresh_token_is_saved_with_issue_time(monkeypatch):
    tokens = {"access_token": "old", "refresh_token": "oldr",
              "refresh_token_obtained_at": 1, "refresh_token_expires_in": 100}
    body = {"access_token": "new", "expires_in": 21599,
            "refresh_token": "newr", "refresh_token_expires_in": 5183999}
    monkeypatch.setattr(kakao.httpx, "post", fake_post(FakeResp(200, body)))
    result = kakao.refresh_tokens(tokens)

    assert result["refresh_token"] == "newr"
    assert result["refresh_token_obtained_at"] == result["obtained_at"]   # 새 발급 시각 기록
    assert result["refresh_token_expires_in"] == 5183999


def test_without_new_refresh_token_keeps_old_meta(monkeypatch):
    tokens = {"access_token": "old", "refresh_token": "oldr",
              "refresh_token_obtained_at": 1, "refresh_token_expires_in": 100}
    body = {"access_token": "new", "expires_in": 21599}
    monkeypatch.setattr(kakao.httpx, "post", fake_post(FakeResp(200, body)))
    result = kakao.refresh_tokens(tokens)

    assert result["refresh_token"] == "oldr"
    assert result["refresh_token_obtained_at"] == 1    # refresh 토큰 발급 시각은 그대로
    assert result["obtained_at"] != 1                  # access 토큰 시각만 갱신된다


def test_expired_refresh_token_requires_reauth(monkeypatch):
    body = {"error": "invalid_grant", "error_code": "KOE322"}
    monkeypatch.setattr(kakao.httpx, "post", fake_post(FakeResp(400, body)))
    with pytest.raises(kakao.KakaoReauthRequired) as excinfo:
        kakao.refresh_tokens({"refresh_token": "secret-refresh-token"})

    assert isinstance(excinfo.value, kakao.KakaoError)        # 기존 오류 처리에도 그대로 걸린다
    assert "secret-refresh-token" not in str(excinfo.value)   # 토큰이 메시지에 나오지 않는다
    assert "try_kakao_auth.py" in str(excinfo.value)


def test_other_refresh_errors_are_not_reauth(monkeypatch):
    body = {"error": "server_error", "error_code": "KOE003"}
    monkeypatch.setattr(kakao.httpx, "post", fake_post(FakeResp(500, body)))
    with pytest.raises(kakao.KakaoError) as excinfo:
        kakao.refresh_tokens({"refresh_token": "r"})

    assert not isinstance(excinfo.value, kakao.KakaoReauthRequired)