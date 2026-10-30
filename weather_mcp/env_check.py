"""서버 시작 시 필수 환경변수를 점검한다. 값은 절대 출력하지 않고 이름만 다룬다."""
import os


def find_missing_env(names: list[str]) -> list[str]:
    """없거나 비어 있는(공백만 있는) 환경변수 이름 목록을 돌려준다."""
    return [n for n in names if not os.environ.get(n, "").strip()]


def require_env(names: list[str]) -> None:
    """하나라도 빠졌으면 빠진 이름을 전부 모아 예외를 낸다 (하나씩 고치는 왕복 방지)."""
    missing = find_missing_env(names)
    if missing:
        # 이름만 적는다. 값(키)이 로그에 남으면 안 된다
        raise RuntimeError("필수 환경변수가 없습니다: " + ", ".join(missing))