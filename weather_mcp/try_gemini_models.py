"""내 Gemini 키로 쓸 수 있는 모델 이름을 출력한다. (키는 출력하지 않는다)"""
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv(Path(__file__).resolve().parent / ".env")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("GEMINI_API_KEY가 설정되지 않았습니다 (.env 확인)")

client = genai.Client(api_key=api_key)

try:
    for model in client.models.list():
        name = model.name or ""
        if "flash" in name.lower():  # 무료 대상인 Flash 계열만 추려서 본다
            print(name)
except errors.APIError as exc:
    # 에러 객체를 통째로 출력하지 않고 종류와 상태 코드만 보여준다 (키 노출 방지)
    print("호출 실패:", type(exc).__name__, getattr(exc, "code", ""))