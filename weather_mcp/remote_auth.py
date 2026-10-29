"""원격 MCP 접근 키 인증. 순수 ASGI 미들웨어라 스트리밍 응답을 방해하지 않는다."""
import json
import os
import secrets
from urllib.parse import parse_qs

MIN_KEY_LENGTH = 32


class RemoteAuthConfigError(RuntimeError):
    """REMOTE_API_KEY 설정이 없거나 너무 짧을 때."""


def load_remote_key(env=None) -> str:
    """환경변수에서 키를 읽는다. 없거나 짧으면 예외 (키 값은 메시지에 넣지 않는다)."""
    env = os.environ if env is None else env
    key = env.get("REMOTE_API_KEY", "")
    if len(key) < MIN_KEY_LENGTH:
        raise RemoteAuthConfigError(
            f"REMOTE_API_KEY가 없거나 {MIN_KEY_LENGTH}자보다 짧습니다."
        )
    return key


def _candidates(scope) -> list[str]:
    """요청에서 키 후보를 모은다: x-api-key 헤더, Bearer 헤더, ?key= 쿼리."""
    found = []
    headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in scope.get("headers", [])
    }
    if "x-api-key" in headers:
        found.append(headers["x-api-key"])
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        found.append(auth[7:].strip())
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    found.extend(query.get("key", []))
    return found


def _matches(candidates: list[str], key: str) -> bool:
    ok = False
    for c in candidates:  # 중간에 멈추지 않고 모두 비교
        if secrets.compare_digest(c.encode("utf-8"), key.encode("utf-8")):
            ok = True
    return ok


async def _respond(send, status: int, body: dict, extra_headers=()):
    payload = json.dumps(body).encode("utf-8")
    headers = [(b"content-type", b"application/json"), *extra_headers]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


class ApiKeyMiddleware:
    def __init__(self, app, api_key: str):
        self.app = app
        self._key = api_key

    async def __call__(self, scope, receive, send):
        # lifespan(서버 시작/종료) 등 http가 아닌 것은 그대로 통과
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["path"] == "/health":  # 상태 확인용, 데이터 없음
            await _respond(send, 200, {"status": "ok"})
            return
        if not _matches(_candidates(scope), self._key):
            # 어떤 값이 틀렸는지 알려 주지 않는다
            await _respond(
                send, 401, {"error": "unauthorized"},
                [(b"www-authenticate", b"Bearer")],
            )
            return
        await self.app(scope, receive, send)