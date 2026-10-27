"""매일 브리핑 발송 진입점 (5-3, 6-1).

실행:  python -m weather_mcp.run_daily
옵션:  --location 지역   (없으면 .env의 DAILY_LOCATION)
       --dry-run         브리핑 문장만 보여 주고 발송·기록은 하지 않는다
       --force           오늘 이미 보냈어도 다시 보낸다 (수동 재발송)
종료 코드: 0 성공 또는 건너뜀, 1 발송 실패, 2 지역 설정 없음

6-1: 저장 방식(발송 이력·토큰)은 store / token_store로 바꿔 끼울 수 있다.
     안 넘기면 지금과 같은 SQLite와 토큰 파일을 쓴다.
"""
import argparse
import functools
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from weather_mcp.services import ai_briefing, history, kakao, kakao_briefing
from weather_mcp.services.store import StoreError

load_dotenv(Path(__file__).resolve().parent / ".env")

CHANNEL = "kakao"
EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2
SKIP_TEXT = {
    "already_sent": "오늘은 이미 발송했습니다",
    "in_progress": "다른 실행이 발송 중입니다",
}
EXTERNAL_FLAG = "USE_EXTERNAL_STORE"


def stores_from_env():
    """USE_EXTERNAL_STORE=1이면 (Postgres 이력, Postgres 토큰), 아니면 (None, None)."""
    if os.getenv(EXTERNAL_FLAG) != "1":
        return None, None
    # 여기서 가져온다: 로컬(SQLite)만 쓸 때는 DB 관련 설정이 없어도 되게
    from weather_mcp.services.pg_history_store import PostgresHistoryStore
    from weather_mcp.services.pg_token_store import PostgresTokenStore
    return PostgresHistoryStore(), PostgresTokenStore()

def parse_args(argv=None):
    """argv가 None이면 명령줄 인자를 읽는다. 테스트에서는 항상 목록을 직접 넘긴다."""
    parser = argparse.ArgumentParser(description="매일 날씨 브리핑을 카카오톡으로 보냅니다.")
    parser.add_argument("--location", help="지역 (없으면 .env의 DAILY_LOCATION)")
    parser.add_argument("--dry-run", action="store_true", help="문장만 만들고 발송·기록은 하지 않음")
    parser.add_argument("--force", action="store_true", help="오늘 이미 보냈어도 다시 보냄")
    return parser.parse_args(argv)


def resolve_location(cli_value):
    """명령줄 값 → 환경변수 순으로 지역을 정한다. 없으면 None."""
    value = (cli_value or os.getenv("DAILY_LOCATION") or "").strip()
    return value or None


def _record(record_id, status, error, store, now):
    """결과를 기록한다. 기록이 실패해도 발송 결과 자체는 바꾸지 않는다."""
    try:
        store.finish_attempt(record_id, status, error=error, now=now)
    except StoreError as exc:
        # StoreError 메시지에는 어떤 작업이 왜 실패했는지(오류 이름)만 들어 있다
        print(f"주의: 발송 이력을 기록하지 못했습니다 ({exc})")


def _dry_run(location, generate):
    """문장만 만들어 보여 준다. 카카오 발송도 이력 기록도 하지 않는다."""
    generate = generate or ai_briefing.generate_briefing
    try:
        result = generate(location, max_chars=kakao_briefing.PROMPT_MAX_CHARS)
    except Exception as exc:  # 예상 못 한 오류는 이름만 보여 준다
        print(f"브리핑 생성 실패: 예상치 못한 오류 ({type(exc).__name__})")
        return EXIT_FAILED
    if "error" in result:
        print(f"브리핑 생성 실패: {result['error']}")
        return EXIT_FAILED
    print(f"[dry-run] {location}\n{result['briefing']}")
    return EXIT_OK


def main(argv=None, send=None, generate=None, db_path=None, now=None,
         store=None, token_store=None) -> int:
    """종료 코드를 반환한다.

    send/generate/db_path/now는 테스트에서 교체한다.
    store: 발송 이력 저장소 (없으면 SQLite, db_path는 이때만 쓴다)
    token_store: 카카오 토큰 저장소 (없으면 토큰 파일)
    """
    args = parse_args(argv)
    location = resolve_location(args.location)
    if not location:
        print("지역이 없습니다. --location 으로 지정하거나 .env에 DAILY_LOCATION을 설정하세요.")
        return EXIT_USAGE

    if args.dry_run:
        return _dry_run(location, generate)
    # 테스트나 직접 지정한 저장소가 없을 때만 환경 스위치를 본다
    if store is None and token_store is None and db_path is None:
        try:
            store, token_store = stores_from_env()
        except (StoreError, kakao.KakaoError) as exc:
            print(f"저장소를 준비하지 못했습니다: {exc}")  # 메시지에 접속 정보는 없다
            return EXIT_FAILED

    # 저장소 정하기: 안 넘기면 지금과 똑같이 동작한다
    store = store or history.SqliteHistoryStore(db_path)
    if send is None and token_store is not None:
        send = functools.partial(kakao.send_text_to_me, store=token_store)

    # 발송권 잡기: 못 잡으면 보내지 않는다 (건너뜀은 실패가 아니다)
    if args.force:
        record_id = store.force_claim(location, CHANNEL, now=now)
    else:
        record_id, reason = store.claim_send(location, CHANNEL, now=now)
        if record_id is None:
            print(f"발송하지 않음: {SKIP_TEXT.get(reason, reason)} ({location})")
            return EXIT_OK

    try:
        result = kakao_briefing.send_briefing_to_kakao(location, generate=generate, send=send)
    except Exception as exc:  # 마지막 안전망: 내용은 노출하지 않고 이름만 남긴다
        result = {"sent": False, "error": f"실행 중 예상치 못한 오류 ({type(exc).__name__})"}

    if result.get("sent"):
        _record(record_id, "sent", None, store, now)
        print(f"발송 완료: {location}")
        return EXIT_OK

    error = result.get("error") or "알 수 없는 오류"
    _record(record_id, "failed", error, store, now)
    print(f"발송 실패: {error}")
    return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())