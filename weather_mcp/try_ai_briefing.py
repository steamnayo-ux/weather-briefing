"""AI 브리핑 전체 흐름 테스트. 기상청 + 에어코리아 + Gemini를 실제로 호출한다."""
import time

from weather_mcp.services import ai_briefing

LOCATION = "서울 강남구"

start = time.monotonic()
result = ai_briefing.generate_briefing(LOCATION)
elapsed = time.monotonic() - start

if "error" in result:
    print("오류:", result["error"])
else:
    print(result["briefing"])
    print()
    print("모델:", result["model"])
    print("생성 시각:", result["generated_at"])
    data = result["data"]
    for name in ("weather", "air"):
        part = data.get(name)
        # 실패한 쪽은 None이라 확인 불가로 표시한다
        print(f"{name} 수집 시각:", part.get("collected_at") if part else "확인 불가")

print("경고:", result.get("warnings"))
print(f"걸린 시간: {elapsed:.1f}초")