"""에이전트를 실제 Gemini·실제 날씨 도구로 한 번 돌려 보는 수동 확인용 스크립트.

사용: python -m weather_mcp.try_agent "내일 해운대에서 러닝해도 돼?"
(프로젝트 루트에서 실행. 실제 API를 호출하므로 자동 테스트에는 넣지 않는다.)
"""
import json
import sys

from weather_mcp.agent import make_gemini_llm, run_agent

sys.stdout.reconfigure(encoding="utf-8")  # 콘솔 한글 깨짐 방지

question = " ".join(sys.argv[1:]) or "내일 해운대에서 러닝해도 돼?"
result = run_agent(question, make_gemini_llm())

print("질문:", question)
print("호출한 도구:")
for call in result["tool_calls"]:
    print("  -", call["name"], json.dumps(call["args"], ensure_ascii=False), "| 오류:", call["error"])
print("LLM 호출 횟수:", result["steps"])
print("\n답변:\n" + result["answer"])