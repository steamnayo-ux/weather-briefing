"""브리핑을 만들어 카카오톡 '나와의 채팅'으로 보내는 서비스 (4-4).

- 브리핑에 error가 있으면 발송하지 않는다 (잘못된 브리핑 방지)
- 문장이 길어도 잘라 보내지 않는다 (kakao.send_text_to_me가 오류로 처리)
- Gemini에는 날씨 데이터만 가고, 카카오에는 완성된 문장만 간다
- 카톡 본문 맨 위에 지역 한 줄을 붙인다 (로그는 Secrets 마스킹으로 지역이 가려지므로)
"""
from weather_mcp.services import ai_briefing, kakao

# AI에게 요청하는 길이. 카카오 한도(kakao.MAX_TEXT_LEN)보다 여유 있게 잡는다
PROMPT_MAX_CHARS = 150

# 카톡 맨 위에 붙이는 지역 줄을 위해 남겨 두는 글자 수 ("📍 " + 지역명 + 줄바꿈)
HEADER_RESERVE = 40
HEADER_PLACE_MAX = 30  # 지역명이 길어도 이 길이까지만 쓴다


def _with_location_header(place, text: str) -> str:
    """브리핑 맨 위에 지역 한 줄을 붙인다. 지역명을 모르면 붙이지 않는다."""
    place = (place or "").strip()
    if not place:
        return text
    return f"📍 {place[:HEADER_PLACE_MAX]}\n{text}"


def send_briefing_to_kakao(location_name: str, generate=None, send=None) -> dict:
    """브리핑을 만들어 나에게 보낸다. generate/send는 테스트에서 교체할 수 있다."""
    # 호출 시점에 정해서 테스트에서 교체할 수 있게 한다
    generate = generate or ai_briefing.generate_briefing
    send = send or kakao.send_text_to_me

    try:
        # 지역 줄이 들어갈 자리를 빼고 AI에게 길이를 요청한다
        max_chars = min(PROMPT_MAX_CHARS, kakao.MAX_TEXT_LEN - HEADER_RESERVE)
        result = generate(location_name, max_chars=max_chars)
        warnings = result.get("warnings", [])

        if "error" in result:  # 데이터/AI 오류 브리핑은 발송하지 않는다
            return {"sent": False, "error": result["error"], "warnings": warnings}

        text = result["briefing"]
        # 확정된 지역명이 있으면 그걸, 없으면 입력한 이름을 쓴다
        message = _with_location_header(result.get("location") or location_name, text)
        try:
            send(message)
        except kakao.KakaoError as exc:  # 메시지에 키·토큰이 없도록 만든 오류
            return {"sent": False, "error": str(exc), "briefing": text,
                    "warnings": warnings}
    except Exception:  # 예상 못 한 오류는 내용을 노출하지 않는다
        return {"sent": False, "error": "브리핑 발송 중 알 수 없는 오류가 발생했습니다."}

    return {
        "sent": True,
        "location": result.get("location"),
        "briefing": text,
        "model": result.get("model"),
        "generated_at": result.get("generated_at"),
        "warnings": warnings,
    }