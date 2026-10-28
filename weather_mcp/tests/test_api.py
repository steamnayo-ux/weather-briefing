"""/chat 엔드포인트 테스트. 가짜 LLM을 주입하므로 네트워크가 필요 없다."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from weather_mcp import api
from weather_mcp.services.ai_briefing import AiError


def text_response(text):
    """도구 요청 없이 텍스트만 있는 응답 (= 최종 답변)."""
    part = SimpleNamespace(text=text, function_call=None, thought=False)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[part]))])


@pytest.fixture
def client():
    """테스트가 끝나면 의존성 교체를 되돌리는 클라이언트."""
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def use_llm(llm):
    api.app.dependency_overrides[api.get_llm] = lambda: llm


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat은_답변과_도구_기록을_돌려준다(client):
    use_llm(lambda contents, config: text_response("내일은 맑아요."))

    response = client.post("/chat", json={"message": "내일 날씨 어때?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "내일은 맑아요."
    assert body["tool_calls"] == []
    assert body["steps"] == 1


def test_앞뒤_공백은_제거하고_에이전트에_전달한다(client):
    received = []

    def llm(contents, config):
        received.append(contents[0].parts[0].text)
        return text_response("네")

    use_llm(llm)
    client.post("/chat", json={"message": "   해운대 날씨   "})

    assert received == ["해운대 날씨"]


@pytest.mark.parametrize("message", ["", "   "])
def test_빈_메시지는_422(client, message):
    use_llm(lambda contents, config: text_response("호출되면 안 됨"))

    response = client.post("/chat", json={"message": message})

    assert response.status_code == 422


def test_message_필드가_없으면_422(client):
    use_llm(lambda contents, config: text_response("호출되면 안 됨"))

    assert client.post("/chat", json={}).status_code == 422


def test_너무_긴_메시지는_422(client):
    use_llm(lambda contents, config: text_response("호출되면 안 됨"))

    response = client.post("/chat", json={"message": "가" * (api.MAX_MESSAGE_CHARS + 1)})

    assert response.status_code == 422


def test_LLM_호출이_실패하면_503(client):
    def failing_llm(contents, config):
        raise AiError("Gemini 호출 실패 (테스트)")

    use_llm(failing_llm)

    response = client.post("/chat", json={"message": "날씨"})

    assert response.status_code == 503
    assert "Gemini 호출 실패" in response.json()["detail"]


def test_API_키가_없으면_503(client, monkeypatch):
    # 의존성을 교체하지 않고 실제 get_llm 이 키 없음을 503 으로 바꾸는지 확인한다.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    response = client.post("/chat", json={"message": "날씨"})

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]