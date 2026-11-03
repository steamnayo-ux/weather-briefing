"""원격 도구 응답·설명 가공 테스트 (warnings -> data_notes, special_weather_report)."""
import asyncio
import inspect

from weather_mcp import remote_server
from weather_mcp.tool_output import (
    SPECIAL_REPORT_TOOLS,
    describe_tool,
    present_tool_result,
    wrap_tool,
)


# ---- present_tool_result ----

def test_warnings는_data_notes로_이름이_바뀐다():
    out = present_tool_result({"temperature_c": 9.0, "warnings": ["예보를 못 가져왔어요"]})
    assert "warnings" not in out
    assert out["data_notes"] == ["예보를 못 가져왔어요"]
    assert out["temperature_c"] == 9.0


def test_빈_warnings도_data_notes로_바뀐다():
    out = present_tool_result({"warnings": []})
    assert out == {"data_notes": []}


def test_특보_필드는_요청한_도구에만_붙는다():
    assert "special_weather_report" not in present_tool_result({"a": 1})
    assert present_tool_result({"a": 1}, add_special_report=True)["special_weather_report"] == "not_provided"


def test_오류_응답에는_특보_필드를_붙이지_않는다():
    out = present_tool_result({"error": "지역을 찾지 못했습니다"}, add_special_report=True)
    assert out == {"error": "지역을 찾지 못했습니다"}


def test_원본_dict를_바꾸지_않는다():
    original = {"warnings": ["x"]}
    present_tool_result(original, add_special_report=True)
    assert original == {"warnings": ["x"]}


def test_dict가_아니면_그대로_돌려준다():
    assert present_tool_result("문자열") == "문자열"
    assert present_tool_result(None) is None


# ---- describe_tool ----

def test_설명의_warnings는_data_notes로_바뀐다():
    def get_weather(location_name: str):
        """현재 날씨. warnings는 내부 알림이며 기상특보가 아니다."""

    text = describe_tool(get_weather)
    assert "warnings" not in text
    assert "data_notes는 내부 알림" in text
    assert "special_weather_report" in text  # get_weather 는 특보 안내 대상


def test_대상이_아닌_도구에는_특보_안내를_붙이지_않는다():
    def get_air_quality(location_name: str):
        """현재 대기질."""

    assert "special_weather_report" not in describe_tool(get_air_quality)


def test_recommend_activity_설명에는_best_window_안내가_붙는다():
    def recommend_activity(location_name: str):
        """활동 추천."""

    assert "best_window" in describe_tool(recommend_activity)


# ---- wrap_tool ----

def test_래퍼는_이름과_시그니처를_보존한다():
    def get_weather(location_name: str, date: str = "오늘") -> dict:
        """설명"""
        return {"warnings": []}

    wrapped = wrap_tool(get_weather)
    assert wrapped.__name__ == "get_weather"
    assert inspect.signature(wrapped) == inspect.signature(get_weather)
    assert wrapped("서울") == {"data_notes": [], "special_weather_report": "not_provided"}


# ---- 실제 원격 서버 등록 결과 ----

def _remote_tools():
    return {t.name: t for t in asyncio.run(remote_server.remote_mcp.list_tools())}


def test_원격에는_허용_목록_6개만_등록된다():
    assert set(_remote_tools()) == {fn.__name__ for fn in remote_server.READ_ONLY_TOOLS}
    assert len(_remote_tools()) == 6


def test_원격_도구_설명에는_warnings가_없다():
    for name, tool in _remote_tools().items():
        assert "warnings" not in (tool.description or ""), name


def test_특보_안내는_해당_도구_설명에_들어_있다():
    tools = _remote_tools()
    for name in SPECIAL_REPORT_TOOLS:
        assert "special_weather_report" in tools[name].description, name


def test_원격_도구의_인자_구조가_원본과_같다():
    tools = _remote_tools()
    for fn in remote_server.READ_ONLY_TOOLS:
        params = inspect.signature(fn).parameters
        schema = tools[fn.__name__].inputSchema
        assert set(schema["properties"]) == set(params), fn.__name__
        required = {n for n, p in params.items() if p.default is inspect.Parameter.empty}
        assert set(schema.get("required", [])) == required, fn.__name__