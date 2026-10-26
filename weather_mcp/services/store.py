"""저장소 인터페이스 (6-1). 저장 방식을 바꿔 끼우기 위한 '약속'만 정의한다.

SQLite, 외부 DB, 파일 등 구현은 따로 둔다. 위쪽 코드(run_daily 등)는 이 약속만 안다.
"""
from datetime import datetime
from typing import Protocol


class StoreError(Exception):
    """저장소 오류. 드라이버 오류(sqlite3.Error 등)를 이 하나로 감싼다.

    메시지에 접속 정보·토큰을 넣지 않는다.
    """


class HistoryStore(Protocol):
    def claim_send(self, location: str, channel: str,
                   now: datetime | None = None) -> tuple[int | None, str]: ...

    def finish_attempt(self, record_id: int, status: str, error: str | None = None,
                       now: datetime | None = None) -> None: ...

    def force_claim(self, location: str, channel: str,
                    now: datetime | None = None) -> int: ...

    def get_record(self, send_date: str, location: str, channel: str) -> dict | None: ...

    def list_recent(self, limit: int = 10) -> list[dict]: ...


class TokenStore(Protocol):
    def load(self) -> dict: ...
    def save(self, tokens: dict) -> None: ...