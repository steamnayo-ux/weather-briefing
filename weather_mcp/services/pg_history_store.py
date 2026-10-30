"""발송 이력의 외부 저장소 (Neon Postgres). HistoryStore 구현.

SqliteHistoryStore와 같은 규칙을 지킨다 (계약 테스트로 확인).
- 중복 방지는 UNIQUE + ON CONFLICT로 DB가 한 번에 판정한다 (조회 후 삽입 금지).
- 시각은 SQLite와 같이 KST ISO 문자열(TEXT)로 저장한다. 문자열 비교가 곧 시간 비교다.
- 오류 메시지에는 접속 정보를 넣지 않고 예외 이름만 넣는다.
"""
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

# 시각 규칙은 history.py 것을 그대로 쓴다 (두 저장소의 '하루' 기준이 어긋나면 안 된다)
from weather_mcp.services.history import (
    ERROR_MAX, STALE_MINUTES, VALID_FINISH, _kst, _text,
)
from weather_mcp.services.store import StoreError

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CONNECT_TIMEOUT_SEC = 15  # 잠든 무료 DB가 깨어나는 시간을 기다린다

CONNECT_RETRY_WAITS = (2, 5)  # 연결 실패 시 2초, 5초 기다렸다 다시 시도 (총 3회)


def _sleep(seconds):
    """테스트에서 실제로 기다리지 않게 바꿔 끼울 수 있도록 따로 둔다."""
    time.sleep(seconds)

SCHEMA = """
CREATE TABLE IF NOT EXISTS send_log (
    id           BIGSERIAL PRIMARY KEY,
    send_date    TEXT NOT NULL,
    location     TEXT NOT NULL,
    channel      TEXT NOT NULL,
    status       TEXT NOT NULL,
    attempted_at TEXT NOT NULL,
    finished_at  TEXT,
    error        TEXT,
    UNIQUE (send_date, location, channel)
)
"""

KEY = "send_date = %s AND location = %s AND channel = %s"


@contextmanager
def _as_store_error(action: str):
    """psycopg 오류를 StoreError로 바꾼다. 연결 문자열이 새지 않게 이름만 남긴다."""
    try:
        yield
    except psycopg.Error as exc:
        raise StoreError(f"{action} 실패: {type(exc).__name__}") from None


class PostgresHistoryStore:
    def __init__(self, database_url=None, schema=None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise StoreError("DATABASE_URL이 없습니다.")
        self.schema = schema  # None이면 기본 공간(실제 운영), 값이 있으면 테스트용 임시 공간

    def _open(self):
        """연결만 재시도한다. 연결 실패는 DB를 건드리기 전이라 반복해도 안전하다."""
        for wait in (*CONNECT_RETRY_WAITS, None):
            try:
                return psycopg.connect(
                    self.database_url,
                    connect_timeout=CONNECT_TIMEOUT_SEC,
                    row_factory=dict_row,
                )
            except psycopg.OperationalError:
                if wait is None:  # 마지막 시도도 실패: 호출한 쪽(_as_store_error)이 이름만 남긴다
                    raise
                _sleep(wait)

    def _connect(self):
        conn = self._open()
        try:
            if self.schema:  # 테스트 전용: 임시 공간을 만들고 그 안에서만 작업한다
                conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
                # LOCAL: 이 트랜잭션 안에서만 유효. 풀러의 서버 연결에 설정이 남지 않는다
                conn.execute(f"SET LOCAL search_path TO {self.schema}")
            else:
                # 운영: 이전 사용자가 남긴 설정과 상관없이 항상 기본 공간을 쓴다
                conn.execute("SET LOCAL search_path TO public")
            conn.execute(SCHEMA)
        except Exception:
            conn.close()
            raise
        return conn

    def claim_send(self, location, channel, now=None):
        moment = _kst(now)
        send_date = moment.strftime("%Y-%m-%d")
        cutoff = _text(moment - timedelta(minutes=STALE_MINUTES))
        with _as_store_error("발송권 확인"), self._connect() as conn:
            # ① 삽입 시도: 충돌하면 에러 없이 0행 → fetchone()이 None
            row = conn.execute(
                "INSERT INTO send_log (send_date, location, channel, status, attempted_at) "
                "VALUES (%s, %s, %s, 'attempting', %s) "
                "ON CONFLICT (send_date, location, channel) DO NOTHING RETURNING id",
                (send_date, location, channel, _text(moment)),
            ).fetchone()
            if row:
                return row["id"], "new"

            # ② 실패했거나 오래 멈춘 행만 되살린다 (조건부 UPDATE 한 문장 = 한 쪽만 성공)
            row = conn.execute(
                "UPDATE send_log SET status = 'attempting', attempted_at = %s, "
                "finished_at = NULL, error = NULL "
                f"WHERE {KEY} "
                "AND (status = 'failed' OR (status = 'attempting' AND attempted_at < %s)) "
                "RETURNING id",
                (_text(moment), send_date, location, channel, cutoff),
            ).fetchone()
            if row:
                return row["id"], "retry"

            # ③ 나머지: 이미 보냈거나, 다른 실행이 시도 중
            row = conn.execute(
                f"SELECT status FROM send_log WHERE {KEY}", (send_date, location, channel)
            ).fetchone()
            if row and row["status"] == "sent":
                return None, "already_sent"
            return None, "in_progress"

    def finish_attempt(self, record_id, status, error=None, now=None):
        if status not in VALID_FINISH:
            raise ValueError("status는 'sent' 또는 'failed'여야 합니다")
        message = error[:ERROR_MAX] if error else None
        with _as_store_error("발송 이력 기록"), self._connect() as conn:
            conn.execute(
                "UPDATE send_log SET status = %s, finished_at = %s, error = %s WHERE id = %s",
                (status, _text(_kst(now)), message, record_id),
            )

    def force_claim(self, location, channel, now=None):
        """상태와 상관없이 오늘 줄을 '시도 중'으로 만든다. 삽입/갱신을 한 문장으로 처리한다."""
        moment = _kst(now)
        with _as_store_error("강제 발송권"), self._connect() as conn:
            row = conn.execute(
                "INSERT INTO send_log (send_date, location, channel, status, attempted_at) "
                "VALUES (%s, %s, %s, 'attempting', %s) "
                "ON CONFLICT (send_date, location, channel) DO UPDATE SET "
                "status = 'attempting', attempted_at = EXCLUDED.attempted_at, "
                "finished_at = NULL, error = NULL "
                "RETURNING id",
                (moment.strftime("%Y-%m-%d"), location, channel, _text(moment)),
            ).fetchone()
            return row["id"]

    def get_record(self, send_date, location, channel):
        with _as_store_error("이력 조회"), self._connect() as conn:
            return conn.execute(
                f"SELECT * FROM send_log WHERE {KEY}", (send_date, location, channel)
            ).fetchone()  # 없으면 None, 있으면 dict

    def list_recent(self, limit=10):
        with _as_store_error("최근 이력 조회"), self._connect() as conn:
            return conn.execute(
                "SELECT * FROM send_log ORDER BY id DESC LIMIT %s", (limit,)
            ).fetchall()