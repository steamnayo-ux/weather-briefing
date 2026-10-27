"""활동 추천 규칙 (러닝·산책·외출·빨래).

판단은 이 파일의 규칙이 하고, AI는 결과를 설명만 한다 (life_index.py와 같은 원칙).
- 안내 문구(reasons, items, notes)에는 숫자를 넣지 않는다. 숫자는 details에 따로 담는다.
- 모르는 값(미세먼지)은 좋다고 단정하지 않고 notes에 '확인하지 못했다'고 남긴다.
- 자외선은 아직 연결 전이라 uv_index가 None이면 규칙이 건너뛴다. 값을 넘기면 바로 작동한다.
"""
from datetime import datetime

from weather_mcp.services import air, weather
from weather_mcp.services.life_index import GRADE_RANK, UMBRELLA_MAYBE, UMBRELLA_MUST

GOOD, CAUTION, AVOID, UNKNOWN = "좋음", "주의", "비추천", "판단불가"
GOOD_REASON = "걸리는 점이 없어요"
NO_HOURS_REASON = "해당 시간대의 예보가 없어요. 이미 지난 시각일 수 있어요"
DUST_UNKNOWN_NOTE = "미세먼지는 확인하지 못했어요"
DUST_TODAY_ONLY_NOTE = "미세먼지는 오늘 측정값만 있어서 이 날짜에는 반영하지 못했어요"

# 질문에 나올 만한 표현 -> 활동 이름 (공백은 지우고 비교한다)
ALIASES = {
    "러닝": "러닝", "달리기": "러닝", "조깅": "러닝",
    "산책": "산책", "걷기": "산책",
    "외출": "외출", "퇴근": "외출", "퇴근길": "외출", "출근": "외출", "출근길": "외출", "우산": "외출",
    "빨래": "빨래", "빨래널기": "빨래", "빨래말리기": "빨래",
}
# 시간을 따로 말하지 않았을 때 보는 시간대 (시작, 끝)
DEFAULT_HOURS = {"러닝": (6, 22), "산책": (7, 21), "외출": (7, 22), "빨래": (9, 18)}
# 미세먼지가 모르는 값일 때 notes를 남길 활동
DUST_MATTERS = ("러닝", "산책")

# 규칙에 쓰는 기준값
DUST_BAD = GRADE_RANK["나쁨"]
DUST_VERY_BAD = GRADE_RANK["매우나쁨"]
RAIN_MAYBE = UMBRELLA_MAYBE   # 강수확률 이 이상이면 '비가 올 수 있음' (%)
RAIN_LIKELY = UMBRELLA_MUST   # 강수확률 이 이상이면 '비가 올 가능성이 높음' (%)
HOT_C = 28                    # 기온 이 이상이면 더움 (°C)
COLD_C = 0                    # 체감온도 이 이하이면 추움 (°C)
UV_HIGH = 6                   # 자외선지수 높음 이상
RUN_WIND_MS = 8               # 러닝: 풍속 이 이상이면 바람이 강함 (m/s)
RUN_AVOID_FEELS_C = -10       # 러닝: 체감온도 이 이하이면 비추천 (°C)
WALK_AVOID_FEELS_C = -15      # 산책: 체감온도 이 이하이면 비추천 (°C)
LAUNDRY_HUMIDITY_PCT = 70     # 빨래: 평균 습도 이 이상이면 잘 안 마름 (%)
LAUNDRY_COLD_C = 5            # 빨래: 최고기온 이 이하이면 천천히 마름 (°C)

GRADE_NAMES = {rank: name for name, rank in GRADE_RANK.items()}


def normalize_activity(name) -> str | None:
    """활동 이름(별칭 포함)을 표준 이름으로 바꾼다. 모르면 None."""
    if not isinstance(name, str):
        return None
    return ALIASES.get(name.replace(" ", ""))


def _is_num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _ge(value, limit) -> bool:
    """값이 숫자이고 limit 이상인가. 값이 없으면 False (모르면 해당 규칙을 적용하지 않는다)."""
    return _is_num(value) and value >= limit


def _le(value, limit) -> bool:
    """값이 숫자이고 limit 이하인가. 값이 없으면 False."""
    return _is_num(value) and value <= limit


def _facts(hourly: dict) -> dict:
    """시간대별 예보에서 규칙이 쓰는 값을 뽑는다. 값이 없으면 None."""
    hours = hourly.get("hours") or []
    summary = hourly.get("summary") or {}
    # 체감온도는 겨울 바람 체감온도가 있으면 그것을, 없으면 기온을 쓴다
    feels = [h.get("wind_chill_c") if h.get("wind_chill_c") is not None else h.get("temperature_c")
             for h in hours]
    feels = [v for v in feels if v is not None]
    humidity = [h["humidity_pct"] for h in hours if h.get("humidity_pct") is not None]
    winds = [h["wind_speed_ms"] for h in hours if h.get("wind_speed_ms") is not None]
    return {
        "temp_min_c": summary.get("temp_min_c"),
        "temp_max_c": summary.get("temp_max_c"),
        "feels_like_min_c": min(feels) if feels else None,
        "precipitation_probability_max": summary.get("precipitation_probability_max"),
        "precipitation_times": summary.get("precipitation_times") or [],
        "humidity_avg_pct": round(sum(humidity) / len(humidity)) if humidity else None,
        "wind_max_ms": max(winds) if winds else None,
    }


# ---- 활동별 규칙: (비추천 이유, 주의 이유, 준비물)을 반환한다 ----

def _rules_running(f: dict, dust: int | None, uv) -> tuple[list, list, list]:
    avoid, caution, items = [], [], []
    if f["precipitation_times"]:
        avoid.append("해당 시간대에 비나 눈이 와요")
    elif _ge(f["precipitation_probability_max"], RAIN_MAYBE):
        caution.append("비가 올 수 있어요")
    if _ge(dust, DUST_BAD):
        avoid.append("미세먼지가 나쁨 이상이라 야외 운동은 피하는 게 좋아요")
    if _le(f["feels_like_min_c"], RUN_AVOID_FEELS_C):
        avoid.append("체감온도가 너무 낮아요")
    if _ge(f["temp_max_c"], HOT_C):
        caution.append("기온이 높아요. 한낮은 피하고 물을 챙기세요")
        items.append("물")
    if _ge(f["wind_max_ms"], RUN_WIND_MS):
        caution.append("바람이 강해요")
    if _ge(uv, UV_HIGH):
        caution.append("자외선이 강해요")
        items.append("자외선 차단제")
    return avoid, caution, items


def _rules_walk(f: dict, dust: int | None, uv) -> tuple[list, list, list]:
    avoid, caution, items = [], [], []
    if f["precipitation_times"]:
        avoid.append("해당 시간대에 비나 눈이 와요")
    elif _ge(f["precipitation_probability_max"], RAIN_MAYBE):
        caution.append("비가 올 수 있어요")
    if _ge(dust, DUST_VERY_BAD):
        avoid.append("미세먼지가 매우 나쁨이에요")
    elif _ge(dust, DUST_BAD):
        caution.append("미세먼지가 나쁨이에요. 마스크를 착용하세요")
        items.append("마스크")
    if _le(f["feels_like_min_c"], WALK_AVOID_FEELS_C):
        avoid.append("체감온도가 너무 낮아요")
    elif _le(f["feels_like_min_c"], COLD_C):
        caution.append("춥게 느껴져요. 따뜻하게 입으세요")
        items.append("따뜻한 겉옷")
    if _ge(f["temp_max_c"], HOT_C):
        caution.append("기온이 높아요. 한낮은 피하고 물을 챙기세요")
        items.append("물")
    if _ge(uv, UV_HIGH):
        caution.append("자외선이 강해요")
        items.append("자외선 차단제")
    return avoid, caution, items


def _rules_outing(f: dict, dust: int | None, uv) -> tuple[list, list, list]:
    """퇴근·외출: 막을 이유는 없고, 준비물(우산·마스크 등)을 알려 주는 것이 목적이다."""
    avoid, caution, items = [], [], []
    pop = f["precipitation_probability_max"]
    if f["precipitation_times"]:
        caution.append("해당 시간대에 비나 눈이 와요")
        items.append("우산")
    elif _ge(pop, RAIN_LIKELY):
        caution.append("비가 올 가능성이 높아요")
        items.append("우산")
    elif _ge(pop, RAIN_MAYBE):
        caution.append("비가 올 수 있어요")
        items.append("작은 우산")
    if _ge(dust, DUST_BAD):
        caution.append("미세먼지가 나쁨 이상이에요")
        items.append("마스크")
    if _le(f["feels_like_min_c"], COLD_C):
        items.append("따뜻한 겉옷")
    if _ge(uv, UV_HIGH):
        items.append("자외선 차단제")
    return avoid, caution, items


def _rules_laundry(f: dict, dust: int | None, uv) -> tuple[list, list, list]:
    avoid, caution, items = [], [], []
    pop = f["precipitation_probability_max"]
    if f["precipitation_times"]:
        avoid.append("해당 시간대에 비나 눈이 와요")
    elif _ge(pop, RAIN_LIKELY):
        avoid.append("비가 올 가능성이 높아요")
    elif _ge(pop, RAIN_MAYBE):
        caution.append("비가 올 수 있어요")
    if _ge(f["humidity_avg_pct"], LAUNDRY_HUMIDITY_PCT):
        caution.append("습도가 높아서 잘 마르지 않아요")
    if _le(f["temp_max_c"], LAUNDRY_COLD_C):
        caution.append("기온이 낮아서 천천히 말라요")
    if _ge(dust, DUST_BAD):
        caution.append("미세먼지가 나쁨 이상이라 실내 건조가 나아요")
    return avoid, caution, items


RULES = {"러닝": _rules_running, "산책": _rules_walk, "외출": _rules_outing, "빨래": _rules_laundry}


def assess_activity(activity: str, hourly: dict, dust_rank: int | None = None,
                    uv_index=None, dust_note: str = DUST_UNKNOWN_NOTE) -> dict:
    """시간대별 예보(get_hourly_forecast 결과)와 대기질 등급 순위로 활동 가능 여부를 판단한다.

    네트워크를 쓰지 않는 순수 함수다.
    dust_rank: 미세먼지 등급 순위 (0 좋음 ~ 3 매우나쁨), 모르면 None
    uv_index: 자외선지수, 모르면 None (규칙을 건너뛴다)
    """
    kind = normalize_activity(activity)
    if kind is None:
        return {"error": f"지원하지 않는 활동입니다: {activity} (지원: 러닝, 산책, 외출, 빨래)"}

    hours = hourly.get("hours") or []
    if not hours:
        return {"activity": kind, "verdict": UNKNOWN, "reasons": [NO_HOURS_REASON],
                "items": [], "notes": [], "details": {}}

    facts = _facts(hourly)
    avoid, caution, items = RULES[kind](facts, dust_rank, uv_index)
    notes = [dust_note] if kind in DUST_MATTERS and dust_rank is None else []
    verdict = AVOID if avoid else CAUTION if caution else GOOD
    return {
        "activity": kind,
        "verdict": verdict,
        "reasons": (avoid + caution) or [GOOD_REASON],
        "items": items,
        "notes": notes,
        "checked_hours": f"{hours[0]['time']}~{hours[-1]['time']}",
        "details": {**facts, "dust_grade": GRADE_NAMES.get(dust_rank), "uv_index": uv_index},
    }


def _worst_dust(air_data) -> int | None:
    """에어코리아 결과에서 PM10·PM2.5 중 더 나쁜 등급의 순위. 모르면 None."""
    if not isinstance(air_data, dict):
        return None
    ranks = []
    for key in ("pm10_grade", "pm25_grade"):
        grade = air_data.get(key)
        if isinstance(grade, str):
            rank = GRADE_RANK.get(grade.replace(" ", ""))
            if rank is not None:
                ranks.append(rank)
    return max(ranks) if ranks else None


def recommend_activity(location_name: str, activity: str, date: str = "오늘",
                       start_hour: int | None = None, end_hour: int | None = None) -> dict:
    """지역·날짜·시간대의 예보와 대기질로 활동(러닝·산책·외출·빨래)을 해도 되는지 판단한다."""
    kind = normalize_activity(activity)
    if kind is None:
        return {"error": f"지원하지 않는 활동입니다: {activity} (지원: 러닝, 산책, 외출, 빨래)"}

    default_start, default_end = DEFAULT_HOURS[kind]
    if start_hour is None and end_hour is None:
        start, end = default_start, default_end
    elif end_hour is None:
        start, end = start_hour, max(default_end, start_hour)
    elif start_hour is None:
        start, end = min(default_start, end_hour), end_hour
    else:
        start, end = start_hour, end_hour

    hourly = weather.get_hourly_forecast(location_name, date, start, end)
    if "error" in hourly:
        return hourly

    # 에어코리아는 '현재 측정값'만 주므로 오늘 판단에만 쓴다
    dust_rank, dust_note = None, DUST_UNKNOWN_NOTE
    if hourly.get("date") == datetime.now(weather.KST).date().isoformat():
        dust_rank = _worst_dust(air.get_air_quality_by_name(location_name))
    else:
        dust_note = DUST_TODAY_ONLY_NOTE

    result = assess_activity(kind, hourly, dust_rank=dust_rank, uv_index=None, dust_note=dust_note)
    return {
        "location": hourly.get("location"),
        "date": hourly.get("date"),
        "collected_at": hourly.get("collected_at"),
        "forecast_base": hourly.get("forecast_base"),
        **result,
        "warnings": hourly.get("warnings", []),
    }