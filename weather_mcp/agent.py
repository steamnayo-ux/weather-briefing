"""대화형 날씨 에이전트: LLM이 도구 호출을 판단하고, 우리가 실행해서 결과를 돌려주는 수동 루프.

흐름
  질문 -> LLM(도구 호출 요청?) -> 도구 실행 -> 결과를 LLM에 전달 -> ... -> 최종 답변

설계 메모
- llm 은 `llm(contents, config) -> response` 형태의 호출 가능 객체다. 테스트에서는 가짜로 갈아 끼운다.
- SDK의 자동 함수 호출은 끈다(disable=True). 도구 실행과 반복 횟수는 이 루프가 직접 통제한다.
- LLM 호출 실패는 AiError 로 올라온다. /chat 엔드포인트(B-4-3)에서 처리한다.
"""
import os
from datetime import datetime

from google.genai import types

from weather_mcp.agent_tools import AGENT_TOOLS
from weather_mcp.services.ai_briefing import GEMINI_MODELS, KST, NEXT_MODEL_CODES, AiError

MAX_STEPS = 5  # LLM 호출 최대 횟수. 도구 호출이 끝없이 이어지는 것을 막는다.
WEEKDAYS = "월화수목금토일"

LIMIT_MESSAGE = "도구를 여러 번 호출했지만 답을 마무리하지 못했어요. 질문을 조금 더 구체적으로 다시 해 주세요."
EMPTY_MESSAGE = "답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요."


def build_system_prompt(now: datetime) -> str:
    """오늘 날짜·시각(KST)을 넣은 시스템 프롬프트. '내일', '모레'를 정확히 해석하게 한다."""
    today = f"{now:%Y-%m-%d}({WEEKDAYS[now.weekday()]}) {now:%H:%M}"
    return f"""당신은 한국 날씨 도우미입니다. 지금은 한국 시각 {today} 입니다.

규칙:
- 날씨·대기질·자외선 수치는 반드시 도구를 호출해서 얻은 값만 사용하세요. 도구 결과에 없는 숫자나 사실을 만들지 마세요.
- 조회할 수 있는 날짜는 오늘·내일·모레뿐입니다. 그 밖의 날짜를 물으면 조회할 수 없다고 안내하세요.
- 질문에 지역이 없으면 도구를 호출하지 말고 어느 지역인지 물어보세요.
- 도구 결과에 ambiguous 가 true 이면 candidates 를 보여 주고 어느 곳인지 되물어보세요.
- 도구 결과에 error 가 있으면 같은 호출을 반복하지 말고, 확인하지 못했다고 쉽게 설명하세요.
- 도구 결과에 headline 이 있으면 답변의 첫 문장으로 그대로 쓰세요. headline 의 판정 표현(verdict)을 더 강하거나 약한 말로 바꾸지 마세요. 그 뒤에 reasons·items 로 이유와 챙길 것을 덧붙이세요.
- 도구 결과의 notes 에 '반영하지 못했다'는 내용이 있으면 한 문장으로 알려 주세요.
- 한 도구의 결과로 다른 영역까지 단정하지 마세요. 예를 들어 대기질 결과만으로 '날씨가 좋다'거나 '야외 활동하기 좋다'고 말하지 마세요. 대기질 질문에는 활동을 권하는 말('무리 없다', '활동하셔도 된다')도 덧붙이지 말고, 활동 가능 여부는 recommend_activity 결과로만 판단하세요.
- 농도 수치를 말할 때는 도구 결과의 unit 을 그대로 쓰세요.
- 답변은 한국어로, 결론을 먼저 말하고 근거를 짧게 덧붙여 2~4문장으로 쓰세요."""


def build_config(system_prompt: str, tools: list) -> types.GenerateContentConfig:
    """Gemini 호출 설정. 자동 함수 호출을 꺼서 수동 루프가 도구 실행을 맡는다."""
    return types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def _run_tool(registry: dict, name: str, args) -> dict:
    """도구 하나를 실행한다. 어떤 실패도 예외 대신 {"error": ...} 로 돌려준다."""
    func = registry.get(name)
    if func is None:
        return {"error": f"알 수 없는 도구입니다: {name}"}
    try:
        result = func(**dict(args or {}))
    except Exception as exc:  # 래퍼(_safe)가 대부분 처리하지만, 가짜 도구 등을 위해 한 번 더 감싼다
        return {"error": f"{type(exc).__name__}: {exc}"}
    return result if isinstance(result, dict) else {"result": result}


def _split_response(response) -> tuple[object, list]:
    """응답에서 (content, parts)를 꺼낸다. 응답이 비어 있으면 (None, [])."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None, []
    content = candidates[0].content
    return content, list(getattr(content, "parts", None) or [])


def run_agent(message: str, llm, tools: list | None = None, now: datetime | None = None,
              max_steps: int = MAX_STEPS) -> dict:
    """질문 하나에 답한다. {"answer", "tool_calls", "steps"} 를 반환한다."""
    tools = AGENT_TOOLS if tools is None else tools
    registry = {fn.__name__: fn for fn in tools}
    config = build_config(build_system_prompt(now or datetime.now(KST)), tools)

    contents = [types.Content(role="user", parts=[types.Part(text=message)])]
    tool_log = []

    for step in range(1, max_steps + 1):
        response = llm(contents, config)
        content, parts = _split_response(response)
        calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        if not calls:  # 도구 요청이 없으면 이것이 최종 답변이다
            text = "".join(
                p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False)
            ).strip()
            return {"answer": text or EMPTY_MESSAGE, "tool_calls": tool_log, "steps": step}

        # LLM의 응답 content 를 가공하지 않고 그대로 이어 붙인다 (모델이 붙인 부가 정보 보존)
        contents.append(content)

        result_parts = []
        for call in calls:
            result = _run_tool(registry, call.name, call.args)
            tool_log.append({
                "name": call.name,
                "args": dict(call.args or {}),
                "error": result.get("error"),
            })
            result_parts.append(types.Part.from_function_response(name=call.name, response=result))
        contents.append(types.Content(role="user", parts=result_parts))

    return {"answer": LIMIT_MESSAGE, "tool_calls": tool_log, "steps": max_steps}


def make_gemini_llm():
    """실제 Gemini 를 부르는 llm. 한 번의 호출 안에서만 기존 브리핑과 같은 모델 폴백을 쓴다."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise AiError("GEMINI_API_KEY가 설정되지 않았습니다 (.env 확인)")

    from google import genai  # 실제로 쓸 때만 불러온다

    client = genai.Client(api_key=api_key)

    def llm(contents, config):
        last_failure = "알 수 없는 오류"
        for model in GEMINI_MODELS:
            try:
                return client.models.generate_content(model=model, contents=contents, config=config)
            except Exception as exc:
                # str(exc)에는 키/URL이 들어갈 수 있어서 이름과 상태 코드만 남긴다
                code = getattr(exc, "code", None)
                last_failure = "Gemini 호출 실패 (" + model + ": " + type(exc).__name__ + " " + str(code or "") + ")"
                if code in NEXT_MODEL_CODES:
                    continue
                raise AiError(last_failure) from None
        raise AiError(last_failure)

    return llm