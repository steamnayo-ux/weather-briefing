"""발송 이력 저장소 (SQLite). 표준 sqlite3만 쓴다.

5-1: 기록과 조회, 5-2: 중복 방지(claim_send).
모든 시각은 한국 시간(KST) ISO 문자열로 저장한다. 형식이 같아서 문자열 비교가 곧 시간 비교다.
error에는 키·토큰·URL이 없는 메시지만 넘겨야 한다 (호출하는 쪽에서 걸러서 보낸다).
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import closing, contextmanager   # contextmanager 추가
from weather_mcp.services.store import StoreError

KST = timezone(timedelta(hours=9))
# 프로젝트 루트의 data 폴더 (.gitignore의 data/*.db* 대상)
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "weather.db"
VALID_FINISH = ("sent", "failed")
ERROR_MAX = 200       # 너무 긴 메시지는 잘라서 저장한다
STALE_MINUTES = 10    # '시도 중'이 이 시간을 넘으면 멈춘 것으로 보고 다시 잡는다

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


def _kst(now: datetime | None) -> datetime:
    """시각을 한국 시간으로 바꾼다. 서버가 UTC여도 한국 날짜 기준으로 기록하기 위해서다."""
    return (now or datetime.now(KST)).astimezone(KST)


def _text(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def add_attempt(location: str, channel: str, db_path=None, now: datetime | None = None) -> int | None:
    """오늘의 첫 시도를 'attempting'으로 기록하고 id를 반환한다.

    같은 날·지역·채널 기록이 이미 있으면 None.
    """
    moment = _kst(now)
    with closing(_connect(db_path)) as conn:
        try:
            with conn:  # 성공하면 commit, 예외가 나면 rollback
                cur = conn.execute(
                    "INSERT INTO send_log (send_date, location, channel, status, attempted_at) "
                    "VALUES (?, ?, ?, 'attempting', ?)",
                    (moment.strftime("%Y-%m-%d"), location, channel, _text(moment)),
                )
        except sqlite3.IntegrityError:
            return None
        return cur.lastrowid


def claim_send(location: str, channel: str, db_path=None, now: datetime | None = None,
               stale_minutes: int = STALE_MINUTES) -> tuple[int | None, str]:
    """발송권을 잡는다. (기록 id 또는 None, 이유)를 반환한다.

    이유: 'new'(첫 시도), 'retry'(실패했거나 오래 멈춘 시도를 다시 잡음),
          'already_sent'(오늘 이미 보냄), 'in_progress'(다른 실행이 시도 중)
    """
    moment = _kst(now)
    record_id = add_attempt(location, channel, db_path=db_path, now=moment)
    if record_id is not None:
        return record_id, "new"

    send_date = moment.strftime("%Y-%m-%d")
    cutoff = _text(moment - timedelta(minutes=stale_minutes))
    with closing(_connect(db_path)) as conn:
        with conn:
            # 조건에 맞을 때만 바꾸는 한 문장이라, 두 실행이 겹쳐도 한 쪽만 성공한다
            cur = conn.execute(
                "UPDATE send_log SET status = 'attempting', attempted_at = ?, "
                "finished_at = NULL, error = NULL "
                "WHERE send_date = ? AND location = ? AND channel = ? "
                "AND (status = 'failed' OR (status = 'attempting' AND attempted_at < ?))",
                (_text(moment), send_date, location, channel, cutoff),
            )
        row = conn.execute(
            "SELECT id, status FROM send_log WHERE send_date = ? AND location = ? AND channel = ?",
            (send_date, location, channel),
        ).fetchone()

    if cur.rowcount == 1 and row:
        return row["id"], "retry"
    if row and row["status"] == "sent":
        return None, "already_sent"
    return None, "in_progress"


def finish_attempt(record_id: int, status: str, error: str | None = None,
                   db_path=None, now: datetime | None = None) -> None:
    """시도 결과를 'sent' 또는 'failed'로 바꾼다."""
    if status not in VALID_FINISH:
        raise ValueError("status는 'sent' 또는 'failed'여야 합니다")
    moment = _kst(now)
    message = error[:ERROR_MAX] if error else None
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute(
                "UPDATE send_log SET status = ?, finished_at = ?, error = ? WHERE id = ?",
                (status, _text(moment), message, record_id),
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



def force_claim(location: str, channel: str, db_path=None, now: datetime | None = None) -> int:
    """수동 재발송용: 상태와 상관없이 오늘 기록을 '시도 중'으로 되돌려 발송권을 잡는다.

    기록이 없으면 새로 만든다. 하루 한 줄 규칙은 그대로라서 같은 줄을 다시 쓴다.
    """
    moment = _kst(now)
    record_id = add_attempt(location, channel, db_path=db_path, now=moment)
    if record_id is not None:
        return record_id

    send_date = moment.strftime("%Y-%m-%d")
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute(
                "UPDATE send_log SET status = 'attempting', attempted_at = ?, "
                "finished_at = NULL, error = NULL "
                "WHERE send_date = ? AND location = ? AND channel = ?",
                (_text(moment), send_date, location, channel),
            )
        row = conn.execute(
            "SELECT id FROM send_log WHERE send_date = ? AND location = ? AND channel = ?",
            (send_date, location, channel),
        ).fetchone()
    return row["id"]

@contextmanager
def _as_store_error(action: str):
    """sqlite3 오류를 StoreError로 바꾼다. 위쪽이 SQLite를 몰라도 되게 하기 위해서다."""
    try:
        yield
    except sqlite3.Error as exc:
        raise StoreError(f"{action} 실패: {type(exc).__name__}") from None


class SqliteHistoryStore:
    """HistoryStore의 SQLite 구현. 위의 함수를 감쌀 뿐, 로직은 복사하지 않는다.

    메서드 안의 claim_send 등은 클래스 메서드가 아니라 모듈의 함수를 가리킨다.
    (테스트에서 history.claim_send를 바꿔도 그대로 따라온다)
    """

    def __init__(self, db_path=None):
        self.db_path = db_path  # db_path는 이제 SQLite 구현 안에만 있다

    def claim_send(self, location, channel, now=None):
        with _as_store_error("발송권 확인"):
            return claim_send(location, channel, db_path=self.db_path, now=now)

    def finish_attempt(self, record_id, status, error=None, now=None):
        with _as_store_error("발송 이력 기록"):
            finish_attempt(record_id, status, error=error, db_path=self.db_path, now=now)

    def force_claim(self, location, channel, now=None):
        with _as_store_error("강제 발송권"):
            return force_claim(location, channel, db_path=self.db_path, now=now)

    def get_record(self, send_date, location, channel):
        with _as_store_error("이력 조회"):
            return get_record(send_date, location, channel, db_path=self.db_path)

    def list_recent(self, limit=10):
        with _as_store_error("최근 이력 조회"):
            return list_recent(limit, db_path=self.db_path)