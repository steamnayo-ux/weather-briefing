"""카카오 토큰 갱신 실제 호출 테스트 (4-3). 토큰 값은 출력하지 않는다."""
from weather_mcp.services import kakao

tokens = kakao.load_tokens()
new_tokens = kakao.refresh_tokens(tokens)
kakao.save_tokens(new_tokens)
print("갱신 성공! access 만료(초):", new_tokens.get("expires_in"))
print("refresh 토큰 교체 여부:", new_tokens["refresh_token"] != tokens["refresh_token"])