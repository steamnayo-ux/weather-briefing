"""발송 이력 저장소 (SQLite). 표준 sqlite3만 쓴다.

5-1은 기록과 조회만 담당한다. 중복 방지 규칙(5-2)은 이 위에 얹는다.
error에는 키·토큰·URL이 없는 메시지만 넘겨야 한다 (호출하는 쪽에서 걸러서 보낸다).
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
# 프로젝트 루트의 data 폴더 (.gitignore의 data/*.db* 대상)
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "weather.db"
VALID_FINISH = ("sent", "failed")
ERROR_MAX = 200  # 너무 긴 메시지는 잘라서 저장한다

SCHEMA = """
CREATE TABLE IF NOT EXISTS send_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    send_date    TEXT NOT NULL,   -- 한국 날짜 'YYYY-MM-DD'
    location     TEXT NOT NULL,
    channel      TEXT NOT NULL,   -- 예: 'kakao'
    status       TEXT NOT NULL,   -- 'attempting' | 'sent' | 'failed'
    attempted_at TEXT NOT NULL,
    finished_at  TEXT,
    error        TEXT,
    UNIQUE (send_date, location, channel)  -- 같은 날·지역·채널은 한 줄만
)
"""


def _connect(db_path=None) -> sqlite3.Connection:
    """DB에 연결한다. 폴더와 표가 없으면 만든다."""
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)  # data 폴더는 git에 없어서 직접 만든다
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # 결과를 열 이름으로 읽는다
    conn.execute(SCHEMA)
    return conn


def _now_text(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def add_attempt(location: str, channel: str, db_path=None, now: datetime | None = None) -> int | None:
    """오늘의 첫 시도를 'attempting'으로 기록하고 id를 반환한다.

    같은 날·지역·채널 기록이 이미 있으면 None (중복 방지는 5-2에서 이 결과를 활용한다).
    """
    moment = now or datetime.now(KST)
    with closing(_connect(db_path)) as conn:
        try:
            with conn:  # 성공하면 commit, 예외가 나면 rollback
                cur = conn.execute(
                    "INSERT INTO send_log (send_date, location, channel, status, attempted_at) "
                    "VALUES (?, ?, ?, 'attempting', ?)",
                    (moment.strftime("%Y-%m-%d"), location, channel, _now_text(moment)),
                )
        except sqlite3.IntegrityError:
            return None
        return cur.lastrowid


def finish_attempt(record_id: int, status: str, error: str | None = None,
                   db_path=None, now: datetime | None = None) -> None:
    """시도 결과를 'sent' 또는 'failed'로 바꾼다."""
    if status not in VALID_FINISH:
        raise ValueError("status는 'sent' 또는 'failed'여야 합니다")
    moment = now or datetime.now(KST)
    message = error[:ERROR_MAX] if error else None
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute(
                "UPDATE send_log SET status = ?, finished_at = ?, error = ? WHERE id = ?",
                (status, _now_text(moment), message, record_id),
            )


def get_record(send_date: str, location: str, channel: str, db_path=None) -> dict | None:
    """해당 날·지역·채널의 기록을 반환한다. 없으면 None."""
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT * FROM send_log WHERE send_date = ? AND location = ? AND channel = ?",
            (send_date, location, channel),
        ).fetchone()
    return dict(row) if row else None


def list_recent(limit: int = 10, db_path=None) -> list[dict]:
    """최근 기록을 새로운 것부터 반환한다."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute("SELECT * FROM send_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]