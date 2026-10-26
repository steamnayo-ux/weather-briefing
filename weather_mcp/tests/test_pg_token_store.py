"""PostgresTokenStore 테스트 (5-6).

실제 DB에는 접속하지 않는다. DB에 닿는 두 메서드(_read_row, _write_row)만 메모리로 바꿔서
암호화·복호화, 재시도, 오류 메시지를 확인한다. (진짜 SQL은 upload_kakao_tokens.py 실행으로 확인한다)
"""
import time

import psycopg
import pytest
from cryptography.fernet import Fernet

from weather_mcp.services import kakao, pg_token_store
from weather_mcp.services.pg_token_store import PostgresTokenStore

KEY = Fernet.generate_key().decode()
SECRET = "secret-refresh-value"  # 저장된 값에 평문으로 남으면 안 되는 문자열
TOKENS = {
    "access_token": "a1",
    "refresh_token": SECRET,
    "obtained_at": 1000,
    "expires_in": 21600,
}


class MemoryTokenStore(PostgresTokenStore):
    """DB 대신 메모리에 저장하는 테스트용. fail_times번까지는 연결 오류를 일으킨다."""

    def __init__(self, key=KEY, fail_times=0):
        super().__init__(database_url="memory://test", encryption_key=key)
        self.rows = {}
        self.fail_times = fail_times
        self.calls = 0

    def _maybe_fail(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise psycopg.OperationalError("테스트용 연결 오류")

    def _read_row(self):
        self._maybe_fail()
        return self.rows.get(self.name)

    def _write_row(self, payload):
        self._maybe_fail()
        self.rows[self.name] = payload


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    """재시도 사이의 대기를 없앤다 (테스트가 느려지지 않게)."""
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


def test_save_then_load_roundtrip():
    store = MemoryTokenStore()
    store.save(TOKENS)
    assert store.load() == TOKENS


def test_stored_payload_is_encrypted():
    store = MemoryTokenStore()
    store.save(TOKENS)
    assert SECRET not in store.rows["kakao"]  # DB에는 평문 토큰이 없다


def test_load_without_saved_tokens_raises():
    with pytest.raises(kakao.KakaoError):
        MemoryTokenStore().load()


def test_wrong_key_raises_clear_error():
    saved = MemoryTokenStore()
    saved.save(TOKENS)
    other = MemoryTokenStore(key=Fernet.generate_key().decode())
    other.rows = saved.rows  # 같은 DB를 다른 키로 읽는 상황
    with pytest.raises(kakao.KakaoError, match="TOKEN_ENCRYPTION_KEY"):
        other.load()


def test_invalid_key_format_raises():
    with pytest.raises(kakao.KakaoError):
        PostgresTokenStore(database_url="memory://test", encryption_key="not-a-key")


def test_missing_database_url_raises(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(kakao.KakaoError, match="DATABASE_URL"):
        PostgresTokenStore(database_url=None, encryption_key=KEY)


def test_transient_failure_is_retried():
    store = MemoryTokenStore(fail_times=2)  # 두 번 실패하고 세 번째에 성공
    store.save(TOKENS)
    assert store.calls == 3
    assert store.load() == TOKENS


def test_permanent_failure_gives_up_without_leaking_connection_info():
    store = MemoryTokenStore(fail_times=99)
    with pytest.raises(kakao.KakaoError) as info:
        store.save(TOKENS)
    assert store.calls == pg_token_store.ATTEMPTS
    assert "memory://" not in str(info.value)  # 접속 정보가 메시지에 없다
    assert "OperationalError" in str(info.value)


def test_exists_reports_saved_state():
    store = MemoryTokenStore()
    assert store.exists() is False
    store.save(TOKENS)
    assert store.exists() is True


def test_send_text_saves_refreshed_tokens_encrypted(monkeypatch):
    """send_text_to_me가 갱신한 토큰을 이 저장소에 암호화해서 넣는지."""

    class OkResponse:
        status_code = 200

        def json(self):
            return {"result_code": 0}

    expired = {**TOKENS, "obtained_at": 0, "expires_in": 0}
    renewed = {**TOKENS, "access_token": "new", "obtained_at": int(time.time()), "expires_in": 21600}
    store = MemoryTokenStore()
    store.save(expired)
    monkeypatch.setattr(kakao, "refresh_tokens", lambda tokens: renewed)
    monkeypatch.setattr(kakao, "_post_message", lambda token, text: OkResponse())

    kakao.send_text_to_me("테스트", store=store)

    assert store.load() == renewed
    assert SECRET not in store.rows["kakao"]