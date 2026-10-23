"""카카오톡 '나에게 보내기' 서비스 (4-3, 5-4).

- 토큰 파일 읽기/저장 (임시 파일에 쓴 뒤 바꿔치기해서 도중에 끊겨도 기존 파일이 남는다)
- access 토큰 만료 임박 시 refresh 토큰으로 갱신
- refresh 토큰의 발급 시각·수명을 따로 기록해 만료 일정을 알 수 있게 한다
- 텍스트 메시지 발송 (401이면 갱신 후 1회만 재시도)

오류 메시지에는 키·토큰·URL을 넣지 않는다.
"""
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

# 토큰 파일 위치: weather_mcp\kakao_tokens.json (gitignore 대상)
TOKEN_FILE = Path(__file__).resolve().parent.parent / "kakao_tokens.json"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
DEFAULT_LINK = "https://www.weather.go.kr"
REFRESH_MARGIN_SEC = 300  # 만료 5분 전부터는 미리 갱신
REFRESH_TTL_DEFAULT_SEC = 5183999  # refresh 토큰 수명(약 60일). 토큰 파일에 값이 없을 때만 쓴다
MAX_TEXT_LEN = 200  # 텍스트 템플릿 글자 수 제한 (콘솔 문서에서 한 번 확인 권장)
TIMEOUT_SEC = 10


class KakaoError(Exception):
    """카카오 연동 오류. 메시지에 키·토큰·URL이 들어가지 않게 한다."""


class KakaoReauthRequired(KakaoError):
    """refresh 토큰이 만료돼 인가 코드로 다시 발급해야 하는 경우."""


def _json(resp) -> dict:
    """응답 본문을 dict로 바꾼다. JSON이 아니면 빈 dict."""
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def load_tokens() -> dict:
    """토큰 파일을 읽는다. 없거나 깨졌으면 KakaoError."""
    if not TOKEN_FILE.exists():
        raise KakaoError("토큰 파일이 없습니다. try_kakao_auth.py로 먼저 발급하세요.")
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except ValueError:
        raise KakaoError("토큰 파일을 읽을 수 없습니다. 토큰을 다시 발급하세요.") from None


def save_tokens(tokens: dict) -> None:
    """토큰을 파일에 저장한다.

    임시 파일에 먼저 쓰고 바꿔치기한다. 새 refresh 토큰이 나오면 기존 것은 폐기되므로,
    쓰다가 끊겨 파일이 깨지면 다시 인증해야 한다. 그 사고를 막기 위한 방식이다.
    """
    tmp = TOKEN_FILE.with_name(TOKEN_FILE.name + ".tmp")
    tmp.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, TOKEN_FILE)


def is_expiring(tokens: dict, now: float | None = None) -> bool:
    """access 토큰이 만료됐거나 곧 만료되면 True. obtained_at이 없으면 True."""
    now = time.time() if now is None else now
    expires_at = tokens.get("obtained_at", 0) + tokens.get("expires_in", 0)
    return now >= expires_at - REFRESH_MARGIN_SEC


def refresh_expires_at(tokens: dict) -> float | None:
    """refresh 토큰이 만료되는 시각(epoch 초). 발급 시각을 모르면 None."""
    issued = tokens.get("refresh_token_obtained_at")
    if not issued:
        return None
    ttl = tokens.get("refresh_token_expires_in") or REFRESH_TTL_DEFAULT_SEC
    return issued + ttl


def refresh_days_left(tokens: dict, now: float | None = None) -> float | None:
    """refresh 토큰이 만료되기까지 남은 날수. 발급 시각을 모르면 None."""
    expires_at = refresh_expires_at(tokens)
    if expires_at is None:
        return None
    now = time.time() if now is None else now
    return (expires_at - now) / 86400


def refresh_tokens(tokens: dict) -> dict:
    """refresh 토큰으로 새 access 토큰을 받아, 갱신된 토큰 dict를 돌려준다."""
    api_key = os.getenv("KAKAO_REST_API_KEY")
    if not api_key:
        raise KakaoError("KAKAO_REST_API_KEY가 .env에 없습니다.")
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise KakaoError("refresh_token이 없습니다. 토큰을 다시 발급하세요.")

    data = {
        "grant_type": "refresh_token",
        "client_id": api_key,
        "refresh_token": refresh_token,
    }
    secret = os.getenv("KAKAO_CLIENT_SECRET")
    if secret:
        data["client_secret"] = secret

    try:
        resp = httpx.post(TOKEN_URL, data=data, timeout=TIMEOUT_SEC)
    except httpx.HTTPError as exc:
        raise KakaoError(f"토큰 갱신 요청 실패: {type(exc).__name__}") from None

    body = _json(resp)
    if resp.status_code != 200 or "access_token" not in body:
        code = body.get("error_code") or body.get("error")
        if code == "KOE322":  # 만료됐거나 폐기된 refresh 토큰
            raise KakaoReauthRequired(
                "refresh 토큰이 만료되었습니다. try_kakao_auth.py로 다시 발급하세요."
            )
        raise KakaoError(f"토큰 갱신 실패: {resp.status_code} {code}")

    new_tokens = dict(tokens)
    new_tokens["access_token"] = body["access_token"]
    new_tokens["expires_in"] = body.get("expires_in", 0)
    new_tokens["obtained_at"] = int(time.time())
    # 새 refresh 토큰은 응답에 있을 때만 교체 (없으면 기존 값과 발급 시각 유지)
    if body.get("refresh_token"):
        new_tokens["refresh_token"] = body["refresh_token"]
        new_tokens["refresh_token_obtained_at"] = new_tokens["obtained_at"]
        if body.get("refresh_token_expires_in"):
            new_tokens["refresh_token_expires_in"] = body["refresh_token_expires_in"]
    return new_tokens


def _post_message(access_token: str, text: str):
    """나에게 보내기 API를 한 번 호출한다."""
    template = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": DEFAULT_LINK, "mobile_web_url": DEFAULT_LINK},
    }
    try:
        return httpx.post(
            SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            # template_object는 JSON '문자열'로 보내야 한다
            data={"template_object": json.dumps(template, ensure_ascii=False)},
            timeout=TIMEOUT_SEC,
        )
    except httpx.HTTPError as exc:
        raise KakaoError(f"발송 요청 실패: {type(exc).__name__}") from None


def send_text_to_me(text: str) -> dict:
    """나와의 채팅에 텍스트를 보낸다.

    1) 만료 임박이면 먼저 갱신  2) 401이면 갱신 후 딱 1번만 재시도
    """
    if not text or not text.strip():
        raise KakaoError("보낼 문장이 비어 있습니다.")
    # 길면 잘라 보내지 않고 오류로 처리 (잘린 브리핑이 나가지 않게)
    if len(text) > MAX_TEXT_LEN:
        raise KakaoError(f"문장이 너무 깁니다 ({len(text)}자 / 최대 {MAX_TEXT_LEN}자).")

    tokens = load_tokens()
    if is_expiring(tokens):
        tokens = refresh_tokens(tokens)
        save_tokens(tokens)

    resp = _post_message(tokens["access_token"], text)
    if resp.status_code == 401:  # access 토큰이 이미 만료된 경우
        tokens = refresh_tokens(tokens)
        save_tokens(tokens)
        resp = _post_message(tokens["access_token"], text)

    body = _json(resp)
    if resp.status_code != 200 or body.get("result_code") != 0:
        raise KakaoError(
            f"발송 실패: {resp.status_code} code={body.get('code')} msg={body.get('msg')}"
        )
    return {"ok": True, "sent_at": int(time.time())}