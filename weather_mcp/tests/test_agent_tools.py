"""agent_tools 래퍼 테스트: 결론 문장(headline)과 모호한 지역 처리. 네트워크가 필요 없다."""
import pytest

from weather_mcp import agent, agent_tools
from weather_mcp.services.location_resolve import LocationAmbiguous


@pytest.mark.parametrize("verdict, phrase", [
    ("좋음", "해도 좋아요"),
    ("주의", "주의가 필요해요"),
    ("비추천", "추천하지 않아요"),
    ("판단불가", "판단하기 어려워요"),
])
def test_판정마다_고정된_결론_표현을_쓴다(verdict, phrase):
    result = {"verdict": verdict, "location": "부산 해운대구", "activity": "러닝", "reasons": ["사유"]}

    headline = agent_tools.make_headline(result, "내일")

    assert headline == f"내일 부산 해운대구 러닝: {phrase} (사유)"


def test_이유가_여러_개면_쉼표로_잇는다():
    result = {"verdict": "주의", "location": "서울 강남구", "activity": "산책",
              "reasons": ["비가 올 수 있어요", "자외선이 강해요"]}

    headline = agent_tools.make_headline(result, "오늘")

    assert headline == "오늘 서울 강남구 산책: 주의가 필요해요 (비가 올 수 있어요, 자외선이 강해요)"


def test_판정이_없는_결과에는_headline이_없다():
    assert agent_tools.make_headline({"error": "지원하지 않는 활동입니다"}, "오늘") is None


def test_recommend_activity는_headline을_맨_앞에_붙인다(monkeypatch):
    fake = {"location": "부산 해운대구", "activity": "러닝", "verdict": "주의", "reasons": ["비가 올 수 있어요"]}
    monkeypatch.setattr(agent_tools, "_recommend_activity", lambda *args: fake)

    result = agent_tools.recommend_activity("해운대", "러닝", "내일")

    assert list(result)[0] == "headline"
    assert result["headline"] == "내일 부산 해운대구 러닝: 주의가 필요해요 (비가 올 수 있어요)"
    assert result["verdict"] == "주의"  # 원래 값은 그대로 남는다


def test_recommend_activity가_오류를_돌려주면_headline없이_그대로_전달한다(monkeypatch):
    monkeypatch.setattr(agent_tools, "_recommend_activity", lambda *args: {"error": "실패"})

    assert agent_tools.recommend_activity("해운대", "러닝", "내일") == {"error": "실패"}


def test_지역이_모호하면_후보를_함께_돌려준다(monkeypatch):
    def ambiguous(*args):
        raise LocationAmbiguous("여러 지역이 있어요", [{"name": "A"}, {"name": "B"}])

    monkeypatch.setattr(agent_tools.weather, "get_weather", ambiguous)

    result = agent_tools.get_weather("중구")

    assert result["ambiguous"] is True
    assert result["candidates"] == [{"name": "A"}, {"name": "B"}]


def test_시스템_프롬프트가_headline을_첫_문장으로_쓰라고_지시한다():
    from datetime import datetime

    prompt = agent.build_system_prompt(datetime(2026, 10, 28, 14, 30, tzinfo=agent.KST))

    assert "headline" in prompt
    assert "단정하지" in prompt  # 한 도구 결과로 다른 영역까지 단정하지 않는다


AIR_RESULT = {"location": "부산 해운대구", "data_time": "2026-10-28 14:00",
              "pm10": 20, "pm10_grade": "좋음", "pm25": 9, "pm25_grade": "좋음"}


def test_대기질_결론_문장을_만든다():
    headline = agent_tools.make_air_headline(AIR_RESULT)

    assert headline == "부산 해운대구 미세먼지(PM10) 좋음, 초미세먼지(PM2.5) 좋음 (2026-10-28 14:00 기준)"


def test_등급이_하나만_있어도_그것만_말한다():
    headline = agent_tools.make_air_headline({"location": "서울 강남구", "pm10_grade": "나쁨", "pm25_grade": None})

    assert headline == "서울 강남구 미세먼지(PM10) 나쁨"


def test_등급이_없으면_대기질_headline이_없다():
    assert agent_tools.make_air_headline({"location": "서울 강남구", "pm10": None}) is None


def test_get_air_quality는_headline과_단위를_붙인다(monkeypatch):
    monkeypatch.setattr(agent_tools.air, "get_air_quality_by_name", lambda name: dict(AIR_RESULT))

    result = agent_tools.get_air_quality("해운대")

    assert list(result)[0] == "headline"
    assert result["unit"] == "㎍/㎥"
    assert result["pm10"] == 20  # 원래 값은 그대로 남는다


def test_get_air_quality가_오류를_돌려주면_그대로_전달한다(monkeypatch):
    monkeypatch.setattr(agent_tools.air, "get_air_quality_by_name", lambda name: {"error": "실패"})

    assert agent_tools.get_air_quality("해운대") == {"error": "실패"}


def test_우산_질문이_활동_추천_도구로_가도록_도구_설명에_적혀_있다():
    # 도구 설명(docstring)이 LLM의 도구 선택을 좌우하므로, 실수로 지워지지 않게 고정한다.
    assert "우산" in agent_tools.recommend_activity.__doc__
    assert "퇴근길" in agent_tools.recommend_activity.__doc__
    assert "recommend_activity" in agent_tools.get_hourly_forecast.__doc__