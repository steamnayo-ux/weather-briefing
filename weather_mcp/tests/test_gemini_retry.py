"""call_gemini 재시도 테스트. 가짜 Gemini 클라이언트를 써서 네트워크를 쓰지 않는다."""
import pytest

from weather_mcp.services import ai_briefing


class FakeApiError(Exception):
    """상태 코드(code)가 있는 가짜 API 오류. 메시지에는 비밀이 들어 있다고 가정한다."""

    def __init__(self, code):
        super().__init__("secret-detail")
        self.code = code


class FakeResponse:
    def __init__(self, text):
        self.text = text


def install_fake_gemini(monkeypatch, outcomes):
    """호출 순서대로 outcomes를 하나씩 꺼내 쓰는 가짜 클라이언트를 설치한다.

    outcomes의 항목이 Exception이면 그 예외를 발생시키고, 문자열이면 응답 문장으로 돌려준다.
    호출된 모델 이름이 쌓이는 리스트를 반환한다.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(ai_briefing.time, "sleep", lambda seconds: None)  # 기다리지 않는다
    calls = []

    class FakeModels:
        def generate_content(self, model, contents):
            calls.append(model)
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return FakeResponse(outcome)

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)
    return calls


def test_retries_on_503_then_succeeds(monkeypatch):
    calls = install_fake_gemini(monkeypatch, [FakeApiError(503), "브리핑 문장"])
    assert ai_briefing.call_gemini("프롬프트") == "브리핑 문장"
    assert len(calls) == 2  # 한 번 실패하고 한 번 재시도


def test_gives_up_after_max_attempts(monkeypatch):
    calls = install_fake_gemini(monkeypatch, [FakeApiError(503)] * ai_briefing.GEMINI_ATTEMPTS)
    with pytest.raises(ai_briefing.AiError) as info:
        ai_briefing.call_gemini("프롬프트")
    assert "503" in str(info.value)
    assert "secret-detail" not in str(info.value)  # 예외 메시지가 새어 나오면 안 된다
    assert len(calls) == ai_briefing.GEMINI_ATTEMPTS


def test_does_not_retry_client_errors(monkeypatch):
    calls = install_fake_gemini(monkeypatch, [FakeApiError(400)])
    with pytest.raises(ai_briefing.AiError):
        ai_briefing.call_gemini("프롬프트")
    assert len(calls) == 1  # 요청 자체가 잘못된 오류는 재시도하지 않는다