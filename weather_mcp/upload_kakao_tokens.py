"""로컬 토큰 파일(kakao_tokens.json)을 DB에 처음 올리는 일회용 스크립트 (5-6).

실행:  python -m weather_mcp.upload_kakao_tokens
       --force   DB에 이미 토큰이 있어도 로컬 파일로 덮어쓴다

DB에 이미 토큰이 있으면 올리지 않는다. 자동 실행이 갱신해 둔 최신 토큰을
오래된 로컬 파일로 덮어쓰는 사고를 막기 위해서다.
토큰 값은 화면에 출력하지 않는다.
종료 코드: 0 성공, 1 실패 또는 올리지 않음
"""
import argparse
import sys

from weather_mcp.services import kakao
from weather_mcp.services.pg_token_store import PostgresTokenStore


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="로컬 카카오 토큰을 DB에 올립니다.")
    parser.add_argument("--force", action="store_true", help="DB에 이미 있어도 덮어씀")
    args = parser.parse_args(argv)

    try:
        local = kakao.FileTokenStore().load()
        db = PostgresTokenStore()
        if db.exists() and not args.force:
            print("DB에 이미 토큰이 있어 올리지 않았습니다. (정말 덮어쓰려면 --force)")
            return 1
        db.save(local)
        back = db.load()  # 다시 읽어서 암호화·복호화까지 한 바퀴 확인한다
    except kakao.KakaoError as exc:
        print(f"실패: {exc}")
        return 1

    same = back == local
    print(f"업로드 완료. 다시 읽은 값이 로컬 파일과 같은가: {'예' if same else '아니오'}")
    days = kakao.refresh_days_left(back)
    if days is not None:
        print(f"refresh 토큰 남은 기간: 약 {days:.0f}일")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())