"""날씨 브리핑을 카카오톡으로 실제 발송하는 테스트 (4-4). 키·토큰은 출력하지 않는다."""
from weather_mcp.services import kakao_briefing

result = kakao_briefing.send_briefing_to_kakao("서울 강남구")
print(result)
if result.get("briefing"):
    print("글자 수:", len(result["briefing"]))