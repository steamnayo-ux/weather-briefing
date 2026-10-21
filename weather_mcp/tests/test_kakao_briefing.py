"""services/kakao_briefing.py와 build_prompt 길이 규칙 테스트. 실제 API는 호출하지 않는다."""
from weather_mcp.services import ai_briefing, kakao, kakao_briefing


def fake_ok(location_name, max_chars=None):
    return {"location": location_name, "briefing": "맑고 기온은 18도입니다.",
            "model": "m", "generated_at": "t", "warnings": []}


def test_sends_when_briefing_ok():
    sent = []
    result = kakao_briefing.send_briefing_to_kakao(
        "서울 강남구", generate=fake_ok, send=lambda text: sent.append(text))
    assert result["sent"] is True
    assert sent == ["맑고 기온은 18도입니다."]


def test_does_not_send_when_briefing_has_error():
    sent = []

    def fake_err(location_name, max_chars=None):
        return {"error": "데이터 없음", "warnings": []}

    result = kakao_briefing.send_briefing_to_kakao(
        "서울 강남구", generate=fake_err, send=lambda text: sent.append(text))
    assert result["sent"] is False
    assert sent == []  # 발송 함수가 아예 호출되지 않아야 한다


def test_passes_prompt_limit_to_generator():
    seen = {}

    def fake(location_name, max_chars=None):
        seen["max_chars"] = max_chars
        return fake_ok(location_name)

    kakao_briefing.send_briefing_to_kakao("서울", generate=fake, send=lambda t: None)
    assert seen["max_chars"] == kakao_briefing.PROMPT_MAX_CHARS


def test_kakao_error_is_returned_not_raised():
    def fake_send(text):
        raise kakao.KakaoError("발송 실패: 401")

    result = kakao_briefing.send_briefing_to_kakao(
        "서울", generate=fake_ok, send=fake_send)
    assert result["sent"] is False
    assert "401" in result["error"]


def test_too_long_briefing_is_not_sent_or_cut():
    def fake_long(location_name, max_chars=None):
        return {"location": "서울", "briefing": "가" * (kakao.MAX_TEXT_LEN + 1),
                "model": "m", "generated_at": "t", "warnings": []}

    # send를 바꾸지 않아도 된다: 길이 검사는 토큰 파일을 읽기 전에 일어난다
    result = kakao_briefing.send_briefing_to_kakao("서울", generate=fake_long)
    assert result["sent"] is False
    assert "너무 깁니다" in result["error"]


def test_unexpected_exception_does_not_leak():
    def boom(location_name, max_chars=None):
        raise RuntimeError("secret-key-123")

    result = kakao_briefing.send_briefing_to_kakao("서울", generate=boom)
    assert result["sent"] is False
    assert "secret-key-123" not in str(result)


def test_build_prompt_without_limit_has_no_length_rule():
    assert "길이 제한" not in ai_briefing.build_prompt({"a": 1})


def test_build_prompt_with_limit_adds_rule():
    prompt = ai_briefing.build_prompt({"a": 1}, max_chars=150)
    assert "길이 제한" in prompt
    assert "150자" in prompt