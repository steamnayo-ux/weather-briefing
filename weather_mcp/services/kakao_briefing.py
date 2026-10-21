"""브리핑을 만들어 카카오톡 '나와의 채팅'으로 보내는 서비스 (4-4).

- 브리핑에 error가 있으면 발송하지 않는다 (잘못된 브리핑 방지)
- 문장이 길어도 잘라 보내지 않는다 (kakao.send_text_to_me가 오류로 처리)
- Gemini에는 날씨 데이터만 가고, 카카오에는 완성된 문장만 간다
"""
from weather_mcp.services import ai_briefing, kakao

# AI에게 요청하는 길이. 카카오 한도(kakao.MAX_TEXT_LEN)보다 여유 있게 잡는다
PROMPT_MAX_CHARS = 150


def send_briefing_to_kakao(location_name: str, generate=None, send=None) -> dict:
    """브리핑을 만들어 나에게 보낸다. generate/send는 테스트에서 교체할 수 있다."""
    # 호출 시점에 정해서 테스트에서 교체할 수 있게 한다
    generate = generate or ai_briefing.generate_briefing
    send = send or kakao.send_text_to_me

    try:
        result = generate(location_name, max_chars=PROMPT_MAX_CHARS)
        warnings = result.get("warnings", [])

        if "error" in result:  # 데이터/AI 오류 브리핑은 발송하지 않는다
            return {"sent": False, "error": result["error"], "warnings": warnings}

        text = result["briefing"]
        try:
            send(text)
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