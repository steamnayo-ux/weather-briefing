"""카카오톡 '나에게 보내기' 고정 문장 발송 테스트 (4-2).
토큰은 kakao_tokens.json에서 읽고, 화면에는 출력하지 않는다."""
import json
from pathlib import Path

import httpx

TOKEN_FILE = Path(__file__).parent / "kakao_tokens.json"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def main() -> None:
    if not TOKEN_FILE.exists():
        print("kakao_tokens.json이 없습니다. try_kakao_auth.py를 먼저 실행하세요.")
        return

    tokens = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    access_token = tokens.get("access_token")

    # 텍스트 템플릿: text(최대 200자)와 link가 필요하다
    template = {
        "object_type": "text",
        "text": "☀️ 날씨 브리핑 테스트 메시지입니다.",
        "link": {
            "web_url": "https://www.weather.go.kr",
            "mobile_web_url": "https://www.weather.go.kr",
        },
    }

    resp = httpx.post(
        SEND_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        # template_object는 JSON '문자열'로 보내야 한다
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=10,
    )

    body = resp.json()
    if resp.status_code == 200 and body.get("result_code") == 0:
        print("발송 성공! 카카오톡 '나와의 채팅'을 확인하세요.")
    else:
        # 토큰이 섞이지 않는 필드만 출력
        print("실패:", resp.status_code, "code:", body.get("code"),
              "msg:", body.get("msg"))


if __name__ == "__main__":
    main()