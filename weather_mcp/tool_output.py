"""원격 MCP(Claude 커넥터)로 나가는 도구 응답과 도구 설명을 다듬는 모듈.

목적: 응답의 'warnings: []'가 '기상특보 없음'으로 오해되는 것을 코드로 막는다.
- 서비스 함수, server.py, 카톡 브리핑은 건드리지 않는다. 원격으로 나가는 응답만 바꾼다.
- warnings -> data_notes : 데이터를 가져오다 생긴 내부 알림 (기상특보가 아니다)
- special_weather_report: "not_provided" : 이 서버는 기상특보를 조회하지 않는다

사용: remote_server.py 에서
    remote_mcp.tool(description=describe_tool(fn))(wrap_tool(fn))
"""
import functools
import inspect

# 날씨 판단에 쓰이는 도구라 특보 오해가 생길 수 있는 도구들
SPECIAL_REPORT_TOOLS = frozenset({"get_weather", "get_hourly_forecast", "recommend_activity"})
SPECIAL_REPORT_VALUE = "not_provided"

# 도구 설명 끝에 덧붙이는 문장 (앞에 공백이 있다)
SPECIAL_REPORT_NOTE = (
    " 응답의 special_weather_report 가 not_provided 이면 이 서버가 기상특보를 조회하지 않았다는 뜻이다."
    " 특보가 없다는 뜻이 아니므로 '특보 없음'이라고 말하지 않고 확인하지 못했다고 안내한다."
)
EXTRA_DESCRIPTIONS = {
    "recommend_activity": (
        " 좋은 시간대를 물으면 best_window(괜찮은 시각이 가장 길게 이어지는 구간, end 는 마지막 예보 시각)를"
        " 그대로 알려 준다. best_window 가 null 이면 괜찮은 시간대가 없다고 말하고 시각을 지어내지 않는다."
    ),
}


def present_tool_result(result, add_special_report: bool = False):
    """도구 결과를 원격용으로 가공한다. 원본 dict 는 바꾸지 않는다.

    - warnings 키는 data_notes 로 이름을 바꾼다.
    - add_special_report 이고 오류 응답이 아니면 special_weather_report 를 붙인다.
    """
    if not isinstance(result, dict):
        return result
    out = dict(result)
    if "warnings" in out:
        out["data_notes"] = out.pop("warnings")
    if add_special_report and "error" not in out:
        out["special_weather_report"] = SPECIAL_REPORT_VALUE
    return out


def describe_tool(fn) -> str:
    """도구 설명(docstring)을 원격용으로 다듬는다.

    docstring 의 'warnings' 는 'data_notes' 로 바꾸고, 필요한 도구에는 안내 문장을 덧붙인다.
    """
    text = inspect.cleandoc(fn.__doc__ or "").replace("warnings", "data_notes")
    if fn.__name__ in SPECIAL_REPORT_TOOLS:
        text += SPECIAL_REPORT_NOTE
    text += EXTRA_DESCRIPTIONS.get(fn.__name__, "")
    return text


def wrap_tool(fn):
    """fn 의 이름·인자·타입 힌트를 그대로 두고 응답만 present_tool_result 로 가공하는 래퍼."""
    add_special = fn.__name__ in SPECIAL_REPORT_TOOLS

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            return present_tool_result(await fn(*args, **kwargs), add_special)
        return async_wrapper

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return present_tool_result(fn(*args, **kwargs), add_special)
    return wrapper