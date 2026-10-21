"""카카오 인가 코드 -> 토큰 1회 발급 테스트 (4-1).
토큰은 화면에 출력하지 않고 kakao_tokens.json(gitignore 대상)에만 저장한다."""
import json
import os
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")
# 콘솔에서 Client Secret을 켠 경우에만 필요 (없으면 비워 둠)
CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET")
# 콘솔에 등록한 값과 한 글자도 다르면 안 됨
REDIRECT_URI = "http://localhost:5000/callback"
AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
TOKEN_FILE = Path(__file__).parent / "kakao_tokens.json"


def extract_code(raw: str) -> str:
    """주소창 전체를 붙여넣어도, code 값만 붙여넣어도 code를 꺼낸다."""
    if "code=" in raw:
        query = urlparse(raw).query or raw
        return parse_qs(query).get("code", [""])[0]
    return raw


def main() -> None:
    if not REST_API_KEY:
        print("KAKAO_REST_API_KEY가 .env에 없습니다.")
        return

    # 1) 로그인/동의 화면 열기 (talk_message 동의를 함께 요청)
    params = {
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "talk_message",
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    if not webbrowser.open(url):
        print("브라우저가 열리지 않으면 아래 주소를 직접 여세요:")
        print(url)
    print("로그인·동의 후 이동한 주소창의 전체 주소(또는 code 값)를 붙여넣으세요.")

    code = extract_code(input("> ").strip())
    if not code:
        print("code를 찾지 못했습니다.")
        return

    # 2) 인가 코드 -> 토큰 교환
    data = {
        "grant_type": "authorization_code",
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }
    if CLIENT_SECRET:
        data["client_secret"] = CLIENT_SECRET

    resp = httpx.post(TOKEN_URL, data=data, timeout=10)
    body = resp.json()

    if resp.status_code != 200:
        # 키·토큰이 섞이지 않는 필드만 출력
        print("실패:", resp.status_code, body.get("error"),
              body.get("error_code"), body.get("error_description"))
        return

    # 3) 파일에 저장 (갱신 로직용 발급 시각 포함). 토큰 값은 출력하지 않는다.
    body["obtained_at"] = int(time.time())
    TOKEN_FILE.write_text(json.dumps(body, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print("성공! 저장 위치:", TOKEN_FILE.name)
    print("access 만료(초):", body.get("expires_in"),
          "/ refresh 만료(초):", body.get("refresh_token_expires_in"))
    print("동의된 scope:", body.get("scope"))


if __name__ == "__main__":
    main()