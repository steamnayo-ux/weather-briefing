"""날씨 에이전트 HTTP API.

실행(프로젝트 루트에서): uvicorn weather_mcp.api:app --reload
확인: 브라우저에서 http://127.0.0.1:8000/docs 를 열어 /chat 을 직접 호출해 본다.

설계 메모
- 요청마다 독립이다(stateless). 대화 기록과 기본 주소는 6단계에서 DB와 함께 넣는다.
- 엔드포인트를 def(동기)로 쓴다. 에이전트가 네트워크를 기다리는 동기 코드라서,
  FastAPI가 알아서 별도 스레드에서 실행해 서버 전체가 멈추지 않는다.
- LLM은 get_llm 의존성으로 받는다. 테스트에서 가짜로 교체할 수 있다.
"""
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from weather_mcp.agent import make_gemini_llm, run_agent
from weather_mcp.services.ai_briefing import AiError

MAX_MESSAGE_CHARS = 500  # 너무 긴 입력으로 비용이 커지는 것을 막는다

app = FastAPI(title="날씨 에이전트")


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=MAX_MESSAGE_CHARS, description="사용자 질문")


def get_llm():
    """실제 Gemini llm 을 만든다. 키가 없으면 서버 오류(500) 대신 503 으로 알린다."""
    try:
        return make_gemini_llm()
    except AiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/health")
def health() -> dict:
    """서버가 살아 있는지 확인하는 용도."""
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest, llm=Depends(get_llm)) -> dict:
    """질문 하나에 답한다. {"answer", "tool_calls", "steps"} 를 반환한다."""
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message 가 비어 있습니다")
    try:
        return run_agent(message, llm)
    except AiError as exc:  # LLM 호출 실패는 우리 서버가 아니라 외부 서비스 문제다
        raise HTTPException(status_code=503, detail=str(exc)) from None