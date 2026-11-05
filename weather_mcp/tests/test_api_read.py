"""읽기 전용 API(/api/...) 테스트. 외부 호출과 DB 는 모두 가짜로 대체한다."""
import pytest
from fastapi.testclient import TestClient

from weather_mcp import api, api_read
from weather_mcp.services import history
from weather_mcp.services.location_resolve import LocationAmbiguous, LocationLookupError


def _make_error(cls, message):
    """생성자 인자 모양과 상관없이 메시지만 가진 예외를 만든다."""
    exc = cls.__new__(cls)
    Exception.__init__(exc, message)
    return exc


@pytest.fixture
def client():
    # raise_server_exceptions=False: 서버 내부 오류도 실제처럼 500 응답으로 받는다
    return TestClient(api.app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def location_ok(monkeypatch):
    """기본은 지역 확인을 통과시킨다. 개별 테스트에서 다시 바꾼다."""
    monkeypatch.setattr(
        api_read.location_service, "get_location", lambda name: {"name": name}
    )


# (주소, 파라미터, 도구 이름, special_weather_report 가 붙어야 하는지)
CASES = [
    ("/api/weather", {"location": "분당구"}, "get_weather", True),
    ("/api/hourly", {"location": "분당구"}, "get_hourly_forecast", True),
    ("/api/recommendations", {"location": "분당구", "activity": "러닝"}, "recommend_activity", True),
    ("/api/air-quality", {"location": "분당구"}, "get_air_quality", False),
    ("/api/uv", {"location": "분당구"}, "get_uv_index", False),
]


@pytest.mark.parametrize("path, params, tool, has_special", CASES)
def test_성공_응답은_data_notes로_바뀌고_특보_미제공이_붙는다(
    client, monkeypatch, path, params, tool, has_special
):
    fake = lambda *a, **k: {"location": "분당구", "warnings": ["일부 예보 누락"]}
    monkeypatch.setattr(api_read.tools, tool, fake)
    response = client.get(path, params=params)
    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["data_notes"] == ["일부 예보 누락"]
    assert "warnings" not in body
    assert ("special_weather_report" in body) is has_special
    if has_special:
        assert body["special_weather_report"] == "not_provided"


@pytest.mark.parametrize("path, params, tool, has_special", CASES)
def test_모호한_지역은_409(client, monkeypatch, path, params, tool, has_special):
    def ambiguous(name):
        raise _make_error(LocationAmbiguous, "후보: 서울 중구, 부산 중구")

    monkeypatch.setattr(api_read.location_service, "get_location", ambiguous)
    response = client.get(path, params=params)
    body = response.json()
    assert response.status_code == 409
    assert body["ok"] is False
    assert body["error"]["code"] == "AMBIGUOUS_LOCATION"
    assert "서울 중구" in body["error"]["message"]


def test_없는_지역은_404(client, monkeypatch):
    monkeypatch.setattr(api_read.location_service, "get_location", lambda name: None)
    response = client.get("/api/weather", params={"location": "없는지역"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "LOCATION_NOT_FOUND"


def test_지역_검색_서비스_오류는_502(client, monkeypatch):
    def broken(name):
        raise _make_error(LocationLookupError, "지역 검색 서비스에 연결하지 못했습니다")

    monkeypatch.setattr(api_read.location_service, "get_location", broken)
    response = client.get("/api/weather", params={"location": "분당구"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"


def test_서비스가_error를_돌려주면_502(client, monkeypatch):
    monkeypatch.setattr(
        api_read.tools, "get_weather", lambda *a, **k: {"error": "기상청 응답을 받지 못했습니다"}
    )
    response = client.get("/api/weather", params={"location": "분당구"})
    body = response.json()
    assert response.status_code == 502
    assert body["error"]["code"] == "UPSTREAM_ERROR"
    assert body["error"]["message"] == "기상청 응답을 받지 못했습니다"


def test_시간_범위를_벗어나면_422(client):
    response = client.get("/api/hourly", params={"location": "분당구", "start_hour": 25})
    body = response.json()
    assert response.status_code == 422
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_PARAM"


def test_시작_시각이_끝_시각보다_크면_422(client):
    response = client.get(
        "/api/hourly", params={"location": "분당구", "start_hour": 20, "end_hour": 8}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PARAM"


def test_지역_파라미터가_없으면_422(client):
    response = client.get("/api/weather")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PARAM"


def test_예상치_못한_오류는_내용을_숨기고_500(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("serviceKey=SECRET_VALUE")

    monkeypatch.setattr(api_read.tools, "get_weather", boom)
    response = client.get("/api/weather", params={"location": "분당구"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "SECRET_VALUE" not in response.text


def test_읽기_API는_발송_이력을_건드리지_않는다(client, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("발송 이력에 접근했습니다")

    for name in ("claim_send", "add_attempt", "finish_attempt", "force_claim"):
        monkeypatch.setattr(history, name, forbidden)
    monkeypatch.setattr(api_read.tools, "get_weather", lambda *a, **k: {"location": "분당구"})
    response = client.get("/api/weather", params={"location": "분당구"})
    assert response.status_code == 200


def test_지역_검색(client, monkeypatch):
    monkeypatch.setattr(
        api_read.tools, "search_location", lambda q: [{"name": "경기 성남시 분당구"}]
    )
    body = client.get("/api/locations/search", params={"q": "분당구"}).json()
    assert body == {"ok": True, "count": 1, "results": [{"name": "경기 성남시 분당구"}]}


def test_health는_두_경로_모두_동작한다(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}


def test_CORS는_로컬_프론트엔드만_허용한다(client):
    headers = {"Access-Control-Request-Method": "GET"}
    allowed = client.options("/api/health", headers={**headers, "Origin": "http://localhost:3000"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    blocked = client.options("/api/health", headers={**headers, "Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers


def test_chat_422는_경로에_따라_오류_형식이_다르다(client):
    """기존 /chat 은 FastAPI 기본 형식, /api/chat 은 새 형식이다."""
    api.app.dependency_overrides[api.get_llm] = lambda: None
    try:
        old = client.post("/chat", json={})
        new = client.post("/api/chat", json={})
    finally:
        api.app.dependency_overrides.pop(api.get_llm, None)
    assert old.status_code == 422 and "detail" in old.json()
    assert new.status_code == 422 and new.json()["ok"] is False


def test_날짜를_이해하지_못하면_422(client, monkeypatch):
    message = "날짜를 이해하지 못했습니다: abc ('오늘', '내일', '모레' 또는 YYYY-MM-DD)"
    monkeypatch.setattr(api_read.tools, "get_hourly_forecast", lambda *a, **k: {"error": message})
    response = client.get("/api/hourly", params={"location": "분당구", "date": "abc"})
    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "INVALID_PARAM"
    assert body["error"]["message"] == message


def test_지원하지_않는_활동은_422(client, monkeypatch):
    message = "지원하지 않는 활동입니다: 없는활동 (지원: 러닝, 산책, 외출, 빨래)"
    monkeypatch.setattr(api_read.tools, "recommend_activity", lambda *a, **k: {"error": message})
    response = client.get(
        "/api/recommendations", params={"location": "분당구", "activity": "없는활동"}
    )
    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "INVALID_PARAM"
    assert "러닝" in body["error"]["message"]


def test_예보_범위_초과_날짜는_422로_올라간다():
    from weather_mcp.api_response import ApiError, ok_body

    # 서비스가 실제로 돌려주는 메시지 (앞부분이 INPUT_ERROR_PREFIXES와 맞아야 한다)
    result = {"error": "단기예보는 오늘부터 모레까지만 조회할 수 있습니다"}

    with pytest.raises(ApiError) as info:
        ok_body(result, "get_hourly_forecast")

    assert info.value.status_code == 422
    assert info.value.code == "INVALID_PARAM"


def test_알_수_없는_서비스_오류는_여전히_502다():
    import pytest
    from weather_mcp.api_response import ApiError, ok_body

    with pytest.raises(ApiError) as info:
        ok_body({"error": "기상청 서버에 연결하지 못했습니다"}, "get_weather")

    assert info.value.status_code == 502
    assert info.value.code == "UPSTREAM_ERROR"