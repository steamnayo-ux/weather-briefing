"""에이전트 루프 테스트. 가짜 LLM과 가짜 도구를 쓰므로 네트워크가 필요 없다."""
from types import SimpleNamespace

from weather_mcp import agent


# ---- 가짜 응답 만들기 ----------------------------------------------------
def text_response(text):
    """도구 요청 없이 텍스트만 있는 응답 (= 최종 답변)."""
    part = SimpleNamespace(text=text, function_call=None, thought=False)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[part]))])


def call_response(name, args):
    """도구 호출을 요청하는 응답."""
    part = SimpleNamespace(text=None, function_call=SimpleNamespace(name=name, args=args), thought=False)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[part]))])


class ScriptedLLM:
    """미리 정한 응답을 순서대로 돌려주고, 호출될 때의 대화 길이를 기록한다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.contents_lengths = []
        self.last_contents = None
        self.last_config = None

    def __call__(self, contents, config):
        self.contents_lengths.append(len(contents))
        self.last_contents = list(contents)
        self.last_config = config
        return self.responses.pop(0)


def get_weather(location_name):
    """가짜 도구: 항상 같은 값을 돌려준다."""
    return {"location": location_name, "temp": 18}


def broken_tool(location_name):
    """가짜 도구: 항상 실패한다."""
    raise RuntimeError("서버 점검 중")


# ---- 테스트 ---------------------------------------------------------------
def test_도구를_호출한_뒤_최종_답변을_돌려준다():
    llm = ScriptedLLM([
        call_response("get_weather", {"location_name": "해운대"}),
        text_response("해운대는 지금 18도예요."),
    ])
    result = agent.run_agent("해운대 날씨 알려줘", llm, tools=[get_weather])

    assert result["answer"] == "해운대는 지금 18도예요."
    assert result["steps"] == 2
    assert result["tool_calls"] == [
        {"name": "get_weather", "args": {"location_name": "해운대"}, "error": None}
    ]
    # 1회차: 질문 1개, 2회차: 질문 + 모델의 도구 요청 + 도구 결과 = 3개
    assert llm.contents_lengths == [1, 3]


def test_도구_결과가_LLM에게_전달된다():
    llm = ScriptedLLM([
        call_response("get_weather", {"location_name": "해운대"}),
        text_response("끝"),
    ])
    agent.run_agent("해운대 날씨", llm, tools=[get_weather])

    sent = llm.last_contents[-1].parts[0].function_response
    assert sent.name == "get_weather"
    assert sent.response == {"location": "해운대", "temp": 18}


def test_도구가_실패하면_에러를_LLM에게_전달하고_계속_진행한다():
    llm = ScriptedLLM([
        call_response("broken_tool", {"location_name": "해운대"}),
        text_response("지금은 확인하지 못했어요."),
    ])
    result = agent.run_agent("날씨", llm, tools=[broken_tool])

    assert result["answer"] == "지금은 확인하지 못했어요."
    assert "RuntimeError" in result["tool_calls"][0]["error"]
    sent = llm.last_contents[-1].parts[0].function_response.response
    assert "서버 점검 중" in sent["error"]


def test_알_수_없는_도구는_에러로_처리한다():
    llm = ScriptedLLM([
        call_response("없는_도구", {}),
        text_response("죄송해요."),
    ])
    result = agent.run_agent("뭐든", llm, tools=[get_weather])

    assert result["tool_calls"][0]["error"] == "알 수 없는 도구입니다: 없는_도구"


def test_인자가_틀려도_루프가_죽지_않는다():
    llm = ScriptedLLM([
        call_response("get_weather", {"wrong_arg": 1}),
        text_response("다시 시도할게요."),
    ])
    result = agent.run_agent("날씨", llm, tools=[get_weather])

    assert result["answer"] == "다시 시도할게요."
    assert result["tool_calls"][0]["error"] is not None


def test_도구를_끝없이_호출하면_최대_횟수에서_멈춘다():
    llm = ScriptedLLM([call_response("get_weather", {"location_name": "해운대"})] * 10)
    result = agent.run_agent("날씨", llm, tools=[get_weather], max_steps=3)

    assert result["answer"] == agent.LIMIT_MESSAGE
    assert result["steps"] == 3
    assert len(result["tool_calls"]) == 3
    assert len(llm.contents_lengths) == 3  # LLM도 3번만 불렀다


def test_빈_응답이면_안내_문구를_돌려준다():
    llm = ScriptedLLM([SimpleNamespace(candidates=[])])
    result = agent.run_agent("날씨", llm, tools=[get_weather])

    assert result["answer"] == agent.EMPTY_MESSAGE


def test_시스템_프롬프트에_오늘_날짜가_들어가고_자동호출은_꺼진다():
    from datetime import datetime

    llm = ScriptedLLM([text_response("네")])
    now = datetime(2026, 10, 28, 14, 30, tzinfo=agent.KST)
    agent.run_agent("안녕", llm, tools=[get_weather], now=now)

    assert "2026-10-28(수) 14:30" in llm.last_config.system_instruction
    assert llm.last_config.automatic_function_calling.disable is True

def test_시스템_프롬프트는_도구의_판정을_바꾸지_말라고_지시한다():
    from datetime import datetime

    prompt = agent.build_system_prompt(datetime(2026, 10, 28, 14, 30, tzinfo=agent.KST))

    assert "verdict" in prompt
    assert "notes" in prompt