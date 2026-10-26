"""카카오 토큰의 외부 저장소 (Neon Postgres). TokenStore 구현 (5-6).

- 토큰 dict를 JSON으로 바꾼 뒤 Fernet(대칭키)으로 암호화해서 저장한다. DB에는 평문 토큰이 없다.
- 접속 정보(DATABASE_URL)와 암호화 키(TOKEN_ENCRYPTION_KEY)는 환경변수에서만 읽는다.
- 갱신으로 받은 새 refresh 토큰을 잃으면 카카오 인증을 처음부터 다시 해야 하므로,
  읽기와 저장은 몇 번 재시도한다. (무료 DB는 한동안 안 쓰면 잠들어서 첫 연결이 느리거나 실패할 수 있다)
- 오류 메시지에는 접속 정보·키·토큰을 넣지 않고 예외 이름만 넣는다.
"""
import json
import os
import time
from pathlib import Path

import psycopg
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

from weather_mcp.services.kakao import KakaoError

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TABLE = "kakao_token_store"  # 고정된 이름이다 (사용자 입력이 아니다)
DEFAULT_NAME = "kakao"       # 한 표에 여러 토큰을 둘 수 있게 이름으로 구분한다
CONNECT_TIMEOUT_SEC = 15     # 잠든 DB가 깨어나는 시간을 넉넉히 기다린다
ATTEMPTS = 3
RETRY_WAIT_SEC = 2

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    name       TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,                      -- 암호화된 토큰 (평문 아님)
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class PostgresTokenStore:
    """TokenStore의 Postgres 구현. load()/save()로 kakao.send_text_to_me(store=...)에 넘긴다."""

    def __init__(self, database_url=None, encryption_key=None, name=DEFAULT_NAME):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        key = encryption_key or os.getenv("TOKEN_ENCRYPTION_KEY")
        if not self.database_url:
            raise KakaoError("DATABASE_URL이 .env에 없습니다.")
        if not key:
            raise KakaoError("TOKEN_ENCRYPTION_KEY가 .env에 없습니다.")
        try:
            self._fernet = Fernet(key)
        except (ValueError, TypeError):
            raise KakaoError("TOKEN_ENCRYPTION_KEY 형식이 올바르지 않습니다.") from None
        self.name = name

    # --- DB에 닿는 부분 (SQL은 여기 두 곳뿐이다. 테스트에서는 이 둘을 바꿔 끼운다) ---
    def _connect(self):
        conn = psycopg.connect(self.database_url, connect_timeout=CONNECT_TIMEOUT_SEC)
        conn.execute(SCHEMA)  # 표가 없으면 만든다
        return conn

    def _read_row(self) -> str | None:
        """암호화된 토큰 문자열을 읽는다. 없으면 None."""
        with self._connect() as conn:  # with를 벗어나면 commit하고 연결을 닫는다
            row = conn.execute(
                f"SELECT payload FROM {TABLE} WHERE name = %s", (self.name,)
            ).fetchone()
        return row[0] if row else None

    def _write_row(self, payload: str) -> None:
        """암호화된 토큰 문자열을 저장한다. 이미 있으면 덮어쓴다."""
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO {TABLE} (name, payload, updated_at) VALUES (%s, %s, now()) "
                "ON CONFLICT (name) DO UPDATE "
                "SET payload = EXCLUDED.payload, updated_at = now()",
                (self.name, payload),
            )

    # --- 재시도와 오류 변환 ---
    def _with_retry(self, action: str, func):
        last = None
        for attempt in range(1, ATTEMPTS + 1):
            try:
                return func()
            except psycopg.Error as exc:
                last = exc
                if attempt < ATTEMPTS:
                    time.sleep(RETRY_WAIT_SEC)
        raise KakaoError(f"토큰 {action} 실패 (DB 오류: {type(last).__name__})") from None

    # --- TokenStore 약속 ---
    def load(self) -> dict:
        payload = self._with_retry("읽기", self._read_row)
        if payload is None:
            raise KakaoError(
                "저장된 카카오 토큰이 없습니다. upload_kakao_tokens.py로 먼저 올리세요."
            )
        try:
            return json.loads(self._fernet.decrypt(payload.encode()).decode())
        except (InvalidToken, ValueError):
            raise KakaoError(
                "저장된 토큰을 풀 수 없습니다. TOKEN_ENCRYPTION_KEY가 맞는지 확인하세요."
            ) from None

    def save(self, tokens: dict) -> None:
        payload = self._fernet.encrypt(
            json.dumps(tokens, ensure_ascii=False).encode()
        ).decode()
        self._with_retry("저장", lambda: self._write_row(payload))

    def exists(self) -> bool:
        """저장된 토큰이 있는지만 확인한다 (내용은 읽지 않는다)."""
        return self._with_retry("확인", self._read_row) is not None