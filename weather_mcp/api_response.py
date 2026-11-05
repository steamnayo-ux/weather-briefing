"""읽기 전용 API 응답 형식.

- 성공: {"ok": true, ...기존 도구 응답...}  (MCP와 같은 가공 규칙을 재사용)
- 실패: {"ok": false, "error": {"code", "message", "candidates"(선택)}}
- 오류 메시지에는 키·URL·토큰·스택트레이스를 넣지 않는다.
"""
from weather_mcp.tool_output import SPECIAL_REPORT_TOOLS, present_tool_result

# 서비스가 {"error": 문자열}로 돌려주는 오류 중, 사용자가 잘못 입력해서 생긴 것의 시작 문장.
# 이런 오류는 상류 서버 문제(502)가 아니라 잘못된 요청(422)이다.
INPUT_ERROR_PREFIXES = (
    "날짜를 이해하지 못했습니다",
    "지원하지 않는 활동입니다",
    "단기예보는 오늘부터 모레까지만",  # 예보 범위를 벗어난 날짜도 사용자 입력 오류
)


class ApiError(Exception):
    """API 응답으로 바꿔 보낼 오류. 상태 코드와 오류 코드를 함께 가진다."""

    def __init__(self, status_code: int, code: str, message: str, candidates=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.candidates = candidates


def error_body(code: str, message: str, candidates=None) -> dict:
    """실패 응답 본문을 만든다."""
    error = {"code": code, "message": message}
    if candidates:
        error["candidates"] = candidates
    return {"ok": False, "error": error}


def ok_body(result: dict, tool_name: str) -> dict:
    """도구 결과를 성공 응답으로 바꾼다. 서비스 오류(error 키)는 종류에 따라 422 또는 502로 올린다."""
    if "error" in result:
        message = str(result["error"])
        if message.startswith(INPUT_ERROR_PREFIXES):
            raise ApiError(422, "INVALID_PARAM", message)
        raise ApiError(502, "UPSTREAM_ERROR", message)
    # 특보 미제공 표시는 MCP와 같은 도구 목록 기준으로 붙인다
    out = present_tool_result(result, tool_name in SPECIAL_REPORT_TOOLS)
    return {"ok": True, **out}