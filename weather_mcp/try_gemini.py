"""Gemini 단독 호출 테스트. 키와 모델 이름이 맞는지, 응답 시간이 얼마나 걸리는지 확인한다."""
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv(Path(__file__).resolve().parent / ".env")

MODEL = "gemini-3.1-flash-lite"  # 에러가 나면 이 값만 바꿔서 다시 시도한다

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("GEMINI_API_KEY가 설정되지 않았습니다 (.env 확인)")

client = genai.Client(api_key=api_key)

start = time.monotonic()
try:
    response = client.models.generate_content(
        model=MODEL,
        contents="한 문장으로 인사해 주세요.",
    )
    elapsed = time.monotonic() - start
    print(response.text)
    usage = response.usage_metadata  # 토큰 사용량
    print("입력 토큰:", getattr(usage, "prompt_token_count", None),
          "/ 출력 토큰:", getattr(usage, "candidates_token_count", None))
    print(f"걸린 시간: {elapsed:.1f}초")
except errors.APIError as exc:
    # 에러 객체를 통째로 출력하지 않고 종류와 상태 코드만 보여준다 (키 노출 방지)
    print("호출 실패:", type(exc).__name__, getattr(exc, "code", ""))