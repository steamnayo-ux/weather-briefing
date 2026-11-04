"""날씨 에이전트 HTTP API.

실행(프로젝트 루트에서): uvicorn weather_mcp.api:app --reload
확인: 브라우저에서 http://127.0.0.1:8000/docs 를 열어 /chat 과 /api/... 를 직접 호출해 본다.

설계 메모
- 요청마다 독립이다(stateless). 대화 기록과 기본 주소는 이후 단계에서 DB와 함께 넣는다.
- 엔드포인트를 def(동기)로 쓴다. 에이전트가 네트워크를 기다리는 동기 코드라서,
  FastAPI가 알아서 별도 스레드에서 실행해 서버 전체가 멈추지 않는다.
- LLM은 get_llm 의존성으로 받는다. 테스트에서는 가짜로 교체할 수 있다.
- /api/... 읽기 전용 엔드포인트는 api_read.py 에 있고, 오류는 {"ok": false, "error": {...}} 형식이다.
  기존 /health, /chat 의 오류 형식은 그대로 둔다.
"""
import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from weather_mcp.agent import make_gemini_llm, run_agent
from weather_mcp.api_read import router as read_router
from weather_mcp.api_response import ApiError, error_body
from weather_mcp.services.ai_briefing import AiError

MAX_MESSAGE_CHARS = 500  # 너무 긴 입력으로 비용이 커지는 것을 막는다.

app = FastAPI(title="날씨 에이전트")

logger = logging.getLogger(__name__)

# 개인용·로컬 전제: 로컬 Next.js 개발 서버에서 오는 요청만 허용한다.
ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(read_router)

HTTP_ERROR_CODES = {404: "NOT_FOUND", 422: "INVALID_PARAM", 503: "SERVICE_UNAVAILABLE"}


def _is_api_path(request: Request) -> bool:
    """/api/ 경로만 새 오류 형식을 쓴다. 기존 /health, /chat 형식은 그대로 둔다."""
    return request.url.path.startswith("/api/")


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    """읽기 전용 API 에서 올린 오류를 {"ok": false, "error": {...}} 로 바꾼다."""
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.candidates),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    """요청 값 검증 실패. /api/ 는 새 형식, 그 외는 FastAPI 기본 형식."""
    if not _is_api_path(request):
        return await request_validation_exception_handler(request, exc)
    # 입력값은 되돌려 보내지 않고 문제가 된 항목 이름만 알린다
    fields = sorted({str(err["loc"][-1]) for err in exc.errors() if err.get("loc")})
    message = "요청 값이 올바르지 않습니다" + (f": {', '.join(fields)}" if fields else "")
    return JSONResponse(status_code=422, content=error_body("INVALID_PARAM", message))


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException):
    """HTTPException 처리. /api/ 는 새 형식, 그 외는 FastAPI 기본 형식."""
    if not _is_api_path(request):
        return await http_exception_handler(request, exc)
    code = HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)))


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """예상치 못한 오류. 예외 내용에 키/URL 이 들어갈 수 있어 이름만 로그에 남기고 응답에는 넣지 않는다."""
    logger.error("예상치 못한 오류: %s", type(exc).__name__)
    if _is_api_path(request):
        return JSONResponse(
            status_code=500, content=error_body("INTERNAL_ERROR", "서버 내부 오류가 발생했습니다")
        )
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=MAX_MESSAGE_CHARS, description="사용자 질문")


def get_llm():
    """실제 Gemini llm 을 만든다. 키가 없으면 서버 오류(500) 대신 503 으로 알린다."""
    try:
        return make_gemini_llm()
    except AiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/api/health")
@app.get("/health")
def health() -> dict:
    """서버가 살아 있는지 확인하는 용도."""
    return {"status": "ok"}


@app.post("/api/chat")
@app.post("/chat")
def chat(request: ChatRequest, llm=Depends(get_llm)) -> dict:
    """질문 하나에 답한다. {"answer", "tool_calls", "steps"} 를 반환한다."""
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message 가 비어 있습니다")
    try:
        return run_agent(message, llm)
    except AiError as exc:  # LLM 호출 실패는 우리 서버가 아니라 외부 서비스 문제다.
        raise HTTPException(status_code=503, detail=str(exc)) from None