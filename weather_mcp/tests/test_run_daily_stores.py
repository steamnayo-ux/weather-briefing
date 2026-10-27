"""run_daily의 저장소 선택 테스트. 실제 DB에는 연결하지 않는다 (객체만 만든다)."""
from cryptography.fernet import Fernet

from weather_mcp import run_daily


def test_flag_off_uses_defaults(monkeypatch):
    monkeypatch.delenv("USE_EXTERNAL_STORE", raising=False)
    assert run_daily.stores_from_env() == (None, None)


def test_flag_on_builds_postgres_stores(monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_STORE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/fake")  # 연결은 안 하므로 가짜로 충분
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    store, token_store = run_daily.stores_from_env()
    assert type(store).__name__ == "PostgresHistoryStore"
    assert type(token_store).__name__ == "PostgresTokenStore"


def test_flag_on_without_database_url_fails(monkeypatch):
    monkeypatch.setenv("USE_EXTERNAL_STORE", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert run_daily.main(["--location", "분당구"]) == run_daily.EXIT_FAILED