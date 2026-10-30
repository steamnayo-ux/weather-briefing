"""PostgresHistoryStore 연결 재시도 테스트. 실제 DB 없이 가짜 연결로 확인한다."""
import psycopg
import pytest

from weather_mcp.services import pg_history_store as mod
from weather_mcp.services.pg_history_store import PostgresHistoryStore
from weather_mcp.services.store import StoreError


class FakeConn:
    def __init__(self, fail_on_execute=False):
        self.closed = False
        self.fail_on_execute = fail_on_execute

    def execute(self, sql, *args):
        if self.fail_on_execute:
            raise psycopg.OperationalError("setup failed")
        return self

    def close(self):
        self.closed = True


@pytest.fixture
def waits(monkeypatch):
    """실제로 기다리지 않고, 기다리려던 시간만 기록한다."""
    recorded = []
    monkeypatch.setattr(mod, "_sleep", recorded.append)
    return recorded


def make_store():
    return PostgresHistoryStore(database_url="postgresql://user:pw@host/db")


def test_연결이_두_번_실패해도_세_번째에_성공하면_연결된다(monkeypatch, waits):
    calls = {"n": 0}

    def fake_connect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise psycopg.OperationalError("db waking up")
        return FakeConn()

    monkeypatch.setattr(mod.psycopg, "connect", fake_connect)
    make_store()._connect()
    assert calls["n"] == 3
    assert waits == [2, 5]


def test_계속_실패하면_StoreError이고_접속정보는_없다(monkeypatch, waits):
    def fake_connect(*args, **kwargs):
        raise psycopg.OperationalError("password=secret host=db")

    monkeypatch.setattr(mod.psycopg, "connect", fake_connect)
    with pytest.raises(StoreError) as exc:
        make_store().claim_send("분당구", "kakao")
    assert "OperationalError" in str(exc.value)
    assert "secret" not in str(exc.value)
    assert waits == [2, 5]


def test_연결_이외의_오류는_재시도하지_않는다(monkeypatch, waits):
    calls = {"n": 0}

    def fake_connect(*args, **kwargs):
        calls["n"] += 1
        raise psycopg.ProgrammingError("bad")

    monkeypatch.setattr(mod.psycopg, "connect", fake_connect)
    with pytest.raises(psycopg.ProgrammingError):
        make_store()._connect()
    assert calls["n"] == 1
    assert waits == []


def test_준비_단계에서_실패하면_연결을_닫는다(monkeypatch, waits):
    conn = FakeConn(fail_on_execute=True)
    monkeypatch.setattr(mod.psycopg, "connect", lambda *a, **k: conn)
    with pytest.raises(psycopg.OperationalError):
        make_store()._connect()
    assert conn.closed is True