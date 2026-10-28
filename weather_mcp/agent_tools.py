"""에이전트(Gemini)에게 노출할 도구 모음.

기존 서비스 함수를 직접 건드리지 않고, LLM이 다루기 쉬운 얇은 래퍼로 감싼다.
- 인자는 단순 타입만 쓴다 (str, int, Literal).
- 반환은 항상 JSON 직렬화 가능한 dict 이다.
- 실패는 예외 대신 {"error": 메시지}로 돌려서, LLM이 사용자에게 설명하게 한다.
- 지역이 모호하면 후보 목록(candidates)을 함께 돌려줘서 LLM이 되묻게 한다.
- 활동 추천은 결론 문장(headline)을 규칙으로 미리 만들어 준다. LLM이 판정 강도를 바꾸지 못하게 하려는 것이다.
"""
import functools
import json
from typing import Literal

from weather_mcp.services import air, location, uv, weather
from weather_mcp.services.activity import AVOID, CAUTION, GOOD, UNKNOWN
from weather_mcp.services.activity import recommend_activity as _recommend_activity
from weather_mcp.services.location_resolve import LocationAmbiguous

# 허용 값을 타입으로 선언한다. SDK가 선언 변환 시 enum으로 바꿔 LLM에 전달한다.
DateText = Literal["오늘", "내일", "모레"]
ActivityName = Literal["러닝", "산책", "외출", "빨래"]

# 판정 -> 결론 표현. 강도가 바뀌지 않도록 판정마다 문구를 고정한다.
VERDICT_PHRASES = {
    GOOD: "해도 좋아요",
    CAUTION: "주의가 필요해요",
    AVOID: "추천하지 않아요",
    UNKNOWN: "판단하기 어려워요",
}


def _to_json_dict(value) -> dict:
    """datetime 등 직렬화가 안 되는 값은 문자열로 바꿔 순수 dict 로 되돌린다."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _safe(func):
    """도구 실행 중 예외가 나도 에이전트 루프가 죽지 않게 감싸는 데코레이터.

    functools.wraps 로 이름·docstring·타입 힌트를 그대로 보존한다.
    (SDK가 함수 선언을 만들 때 이 정보를 읽기 때문에 반드시 필요하다.)
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return _to_json_dict(func(*args, **kwargs))
        except LocationAmbiguous as e:
            # 반드시 아래 except Exception 보다 위에 둔다 (자식 예외가 먼저 잡혀야 한다)
            return _to_json_dict({
                "error": str(e),
                "ambiguous": True,
                "candidates": e.candidates[:5],
            })
        except Exception as e:  # 그 외 오류(LocationError 등)
            return {"error": f"{type(e).__name__}: {e}"}
    return wrapper


AIR_UNIT = "㎍/㎥"  # 에어코리아 미세먼지 농도 단위 (LLM이 ㎛ 로 잘못 쓰는 것을 막는다)


def make_air_headline(result: dict) -> str | None:
    """대기질 결과로 결론 문장을 만든다. 등급이 하나도 없으면 None.

    예) '부산 해운대구 미세먼지(PM10) 좋음, 초미세먼지(PM2.5) 좋음 (2026-10-28 14:00 기준)'
    """
    parts = [
        f"{label} {result[key]}"
        for label, key in (("미세먼지(PM10)", "pm10_grade"), ("초미세먼지(PM2.5)", "pm25_grade"))
        if isinstance(result.get(key), str)
    ]
    if not parts:
        return None
    headline = " ".join(p for p in (result.get("location"), ", ".join(parts)) if p)
    return f"{headline} ({result['data_time']} 기준)" if result.get("data_time") else headline


def make_headline(result: dict, date: str) -> str | None:
    """활동 추천 결과로 결론 문장을 만든다. 판정이 없으면(오류 등) None.

    예) '내일 부산 해운대구 러닝: 주의가 필요해요 (비가 올 수 있어요)'
    """
    phrase = VERDICT_PHRASES.get(result.get("verdict"))
    if phrase is None:
        return None
    subject = " ".join(p for p in (date, result.get("location"), result.get("activity")) if p)
    reasons = ", ".join(result.get("reasons") or [])
    headline = f"{subject}: {phrase}"
    return f"{headline} ({reasons})" if reasons else headline


@_safe
def search_location(query: str) -> dict:
    """장소 이름이나 주소로 위치 후보를 검색한다.
    지역 이름이 모호하거나 어느 곳인지 확인해야 할 때만 쓴다.
    다른 도구는 지역 이름을 직접 받으므로, 보통은 먼저 호출할 필요가 없다.
    """
    return {"results": location.search_location(query)}


@_safe
def get_weather(location_name: str) -> dict:
    """지역의 '현재' 날씨와 오늘 하루 요약(최저·최고기온, 최대 강수확률)을 알려준다.
    지금 날씨, 오늘 대략적인 날씨를 물을 때 쓴다.
    내일·모레나 시간대별 질문에는 get_hourly_forecast 를 쓴다.
    """
    return weather.get_weather(location_name)


@_safe
def get_hourly_forecast(
    location_name: str,
    date: DateText = "오늘",
    start_hour: int = 0,
    end_hour: int = 23,
) -> dict:
    """지역의 시간대별 예보(기온·강수·바람 등)를 알려준다.
    date 는 '오늘', '내일', '모레' 중 하나. start_hour~end_hour 는 0~23 시(포함).
    '내일 오후에 비 와?', '저녁 기온은?' 같은 날짜·시간 질문에 쓴다.
    우산이 필요한지, 활동을 해도 되는지 같은 '판단' 질문에는 쓰지 말고 recommend_activity 를 쓴다.
    """
    return weather.get_hourly_forecast(location_name, date, start_hour, end_hour)


@_safe
def get_uv_index(
    location_name: str,
    date: DateText = "오늘",
    start_hour: int = 0,
    end_hour: int = 23,
) -> dict:
    """지역의 자외선지수를 알려준다 (구간 내 최대값과 단계).
    date 는 '오늘', '내일', '모레' 중 하나. start_hour~end_hour 는 0~23 시(포함).
    선크림, 자외선, 햇볕 질문에 쓴다.
    """
    # now 는 숨기고, 에러를 dict 로 돌려주는 MCP용 함수를 그대로 사용한다.
    return uv.lookup_uv_index(location_name, date, start_hour, end_hour)


@_safe
def get_air_quality(location_name: str) -> dict:
    """지역의 현재 대기질(미세먼지·초미세먼지 등)을 알려준다.
    미세먼지, 공기 질, 마스크 질문에 쓴다. 대기질만 알려주며 날씨·활동 가능 여부는 알려주지 않는다.
    결과의 headline 은 규칙이 만든 결론 문장이다.
    """
    result = air.get_air_quality_by_name(location_name)
    if not isinstance(result, dict) or "error" in result:
        return result
    extra = {}
    headline = make_air_headline(result)
    if headline:
        extra["headline"] = headline
    if "pm10" in result or "pm25" in result:
        extra["unit"] = AIR_UNIT
    return {**extra, **result}  # headline 을 맨 앞에 둔다


@_safe
def recommend_activity(
    location_name: str,
    activity: ActivityName,
    date: DateText = "오늘",
    start_hour: int | None = None,
    end_hour: int | None = None,
) -> dict:
    """활동을 해도 되는지 종합 판단한다 (예보·대기질·자외선 반영).
    activity 는 '러닝', '산책', '외출', '빨래' 중 하나.
    우산이 필요한지, 출근길·퇴근길 날씨는 '외출'로 묻는다.
    date 는 '오늘', '내일', '모레' 중 하나. 시간대를 말했을 때만 start_hour, end_hour 를 채운다.
    (예: 출근길은 7~9시, 퇴근길은 17~20시, 아침은 6~9시)
    '러닝해도 돼?', '빨래 널어도 돼?', '우산 필요해?' 처럼 해도 되는지·필요한지 묻는 질문에는 이 도구를 먼저 쓴다.
    결과의 headline 은 규칙이 만든 결론 문장이다.
    """
    result = _recommend_activity(location_name, activity, date, start_hour, end_hour)
    headline = make_headline(result, date)
    # headline 을 맨 앞에 둔다 (LLM이 가장 먼저 보게 한다)
    return {"headline": headline, **result} if headline else result


# 에이전트에게 넘길 도구 목록 (B-4-2에서 Gemini 설정에 그대로 전달한다).
AGENT_TOOLS = [
    search_location,
    get_weather,
    get_hourly_forecast,
    get_uv_index,
    get_air_quality,
    recommend_activity,
]