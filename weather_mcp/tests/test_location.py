"""location.py 테스트. 실제 카카오 API 호출 없이 가짜 응답만 사용한다."""
import httpx
import pytest

from weather_mcp.services import air, location, weather
from weather_mcp.services.location_resolve import (
    LocationAmbiguous,
    LocationError,
    LocationLookupError,
)


def addr(name, x="127.0", y="37.5"):
    """주소 검색 응답 문서 흉내 (x=경도, y=위도, 문자열)."""
    return {"address_name": name, "x": x, "y": y}


def place(place_name, address, x="127.0", y="37.5"):
    """키워드 검색 응답 문서 흉내."""
    return {"place_name": place_name, "address_name": address, "x": x, "y": y}


def patch_kakao(monkeypatch, address=None, keyword=None):
    """location._call_kakao를 가짜로 바꾸고, 호출 기록 [(kind, query), ...]을 돌려준다."""
    calls = []

    def fake(kind, query):
        calls.append((kind, query))
        return list((address if kind == "address" else keyword) or [])

    monkeypatch.setattr(location, "_call_kakao", fake)
    return calls


class FakeResp:
    """httpx 응답 흉내."""

    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code = status
        self._body = body
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("json 아님")
        return self._body


# ---------- 오류 계층 ----------

def test_오류_계층():
    assert issubclass(LocationAmbiguous, LocationError)
    assert issubclass(LocationLookupError, LocationError)


# ---------- get_location / search_location ----------

def test_주소_한_건이면_확정하고_키워드는_호출하지_않는다(monkeypatch):
    calls = patch_kakao(monkeypatch, address=[addr("서울 강남구", x="127.047", y="37.517")])
    loc = location.get_location("강남")
    assert loc["name"] == "서울 강남구"
    assert loc["lat"] == 37.517 and loc["lon"] == 127.047
    assert calls == [("address", "강남")]


def test_주소_0건이면_키워드로_대체(monkeypatch):
    calls = patch_kakao(monkeypatch, address=[], keyword=[
        place("판교역", "경기 성남시 분당구 삼평동 681", x="127.111", y="37.394"),
    ])
    loc = location.get_location("판교역")
    assert loc["name"] == "경기 성남시 분당구"
    assert loc["place_name"] == "판교역"
    assert calls == [("address", "판교역"), ("keyword", "판교역")]


def test_여러_지역이면_LocationAmbiguous(monkeypatch):
    patch_kakao(monkeypatch, address=[addr("서울 중구"), addr("인천 영종구")])
    with pytest.raises(LocationAmbiguous) as exc:
        location.get_location("중구")
    assert "서울 중구" in str(exc.value)


def test_결과가_없으면_None(monkeypatch):
    patch_kakao(monkeypatch, address=[], keyword=[])
    assert location.get_location("없는지역xyz") is None


def test_빈_검색어는_API를_부르지_않고_None_또는_빈_목록(monkeypatch):
    calls = patch_kakao(monkeypatch, address=[addr("서울 강남구")])
    assert location.get_location("   ") is None
    assert location.search_location("") == []
    assert calls == []


def test_공백은_정리해서_검색(monkeypatch):
    calls = patch_kakao(monkeypatch, address=[addr("서울 강남구")])
    location.get_location("  서울   강남구 ")
    assert calls == [("address", "서울 강남구")]


def test_search_location은_여러_곳이어도_후보_전체를_돌려준다(monkeypatch):
    patch_kakao(monkeypatch, address=[addr("서울 중구"), addr("인천 영종구")])
    result = location.search_location("중구")
    assert [c["name"] for c in result] == ["서울 중구", "인천 영종구"]


# ---------- 캐시 ----------

def test_같은_검색어는_캐시를_써서_API를_한_번만_부른다(monkeypatch):
    calls = patch_kakao(monkeypatch, address=[addr("서울 강남구")])
    location.get_location("강남")
    location.get_location("강남")
    assert calls == [("address", "강남")]


def test_실패는_캐시하지_않고_다음에_다시_시도한다(monkeypatch):
    attempts = []

    def flaky(kind, query):
        attempts.append(kind)
        if len(attempts) == 1:
            raise LocationLookupError("연결 실패")
        return [addr("서울 강남구")]

    monkeypatch.setattr(location, "_call_kakao", flaky)
    with pytest.raises(LocationLookupError):
        location.get_location("강남")
    assert location.get_location("강남")["name"] == "서울 강남구"
    assert len(attempts) == 2


def test_서비스_장애는_None이_아니라_LocationLookupError(monkeypatch):
    def down(kind, query):
        raise LocationLookupError("연결 실패")

    monkeypatch.setattr(location, "_call_kakao", down)
    with pytest.raises(LocationLookupError):
        location.get_location("강남")


# ---------- 응답 해석 / HTTP 호출 ----------

def test_parse_정상_응답은_documents를_돌려준다():
    assert location._parse_response(200, {"documents": [{"a": 1}]}) == [{"a": 1}]


@pytest.mark.parametrize("status", [401, 403])
def test_parse_권한_오류_메시지(status):
    with pytest.raises(LocationLookupError) as exc:
        location._parse_response(status, {"message": "secret-detail"})
    assert "카카오맵" in str(exc.value)
    assert "secret-detail" not in str(exc.value)  # 응답 본문은 노출하지 않는다


def test_parse_그_외_상태_코드():
    with pytest.raises(LocationLookupError) as exc:
        location._parse_response(500, None)
    assert "500" in str(exc.value)


@pytest.mark.parametrize("body", [None, {}, {"documents": "x"}, ["a"]])
def test_parse_형식이_이상하면_오류(body):
    with pytest.raises(LocationLookupError):
        location._parse_response(200, body)


def test_call_kakao는_키를_헤더에_담아_호출한다(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key-123")
    seen = {}

    def fake_get(url, headers, params, timeout):
        seen.update(url=url, headers=headers, params=params)
        return FakeResp(200, {"documents": [addr("서울 강남구")]})

    monkeypatch.setattr(location.httpx, "get", fake_get)
    docs = location._call_kakao("address", "강남")
    assert docs == [addr("서울 강남구")]
    assert seen["url"].endswith("/address.json")
    assert seen["headers"]["Authorization"] == "KakaoAK test-key-123"
    assert seen["params"] == {"query": "강남"}


def test_call_kakao는_키가_없으면_호출하지_않고_오류(monkeypatch):
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    # httpx.get은 conftest가 막아 두었으므로, 호출했다면 AssertionError로 실패한다
    with pytest.raises(LocationLookupError) as exc:
        location._call_kakao("address", "강남")
    assert "KAKAO_REST_API_KEY" in str(exc.value)


def test_call_kakao_네트워크_오류에는_키와_URL이_새지_않는다(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key-123")

    def boom(url, headers, params, timeout):
        raise httpx.ConnectError("https://dapi.kakao.com/x KakaoAK test-key-123")

    monkeypatch.setattr(location.httpx, "get", boom)
    with pytest.raises(LocationLookupError) as exc:
        location._call_kakao("address", "강남")
    assert "test-key-123" not in str(exc.value)
    assert "kakao.com" not in str(exc.value)


def test_call_kakao_json이_아닌_응답은_형식_오류(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key-123")
    monkeypatch.setattr(location.httpx, "get",
                        lambda url, headers, params, timeout: FakeResp(200, bad_json=True))
    with pytest.raises(LocationLookupError):
        location._call_kakao("address", "강남")


# ---------- 안전장치 ----------

def test_테스트에서는_실제_HTTP_호출이_막혀_있다():
    with pytest.raises(AssertionError):
        httpx.get("https://example.com")


# ---------- air / weather 연결 ----------

@pytest.mark.parametrize("exc", [
    LocationAmbiguous("지역이 여러 곳입니다: A, B", []),
    LocationLookupError("지역 검색 서비스에 연결하지 못했습니다"),
])
def test_air는_지역_오류를_error로_바꿔_돌려준다(monkeypatch, exc):
    def boom(name):
        raise exc

    monkeypatch.setattr(air, "get_location", boom)
    assert air.get_air_quality_by_name("중구") == {"error": str(exc)}


@pytest.mark.parametrize("exc", [
    LocationAmbiguous("지역이 여러 곳입니다: A, B", []),
    LocationLookupError("지역 검색 서비스에 연결하지 못했습니다"),
])
def test_weather는_지역_오류를_error로_바꿔_돌려준다(monkeypatch, exc):
    def boom(name):
        raise exc

    monkeypatch.setattr(weather, "get_location", boom)
    assert weather.get_weather("중구") == {"error": str(exc)}
