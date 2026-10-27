"""날씨·대기질 데이터에서 우산·옷차림·미세먼지 안내를 정하는 규칙 (생활지수).

판단은 이 파일의 규칙이 하고, AI는 결과를 문장으로 다듬기만 한다.
안내 문구에는 숫자를 넣지 않는다 (AI 문장의 '데이터에 없는 숫자' 검사에 걸리지 않게).
말할 필요가 없는 항목(비 올 가능성이 낮음, 미세먼지 보통 이하)은 만들지 않는다.
"""

# 우산: 강수확률 기준 (%)
UMBRELLA_MUST = 60
UMBRELLA_MAYBE = 30

# 옷차림: (이 기온 이상이면, 문구). 위에서부터 처음 맞는 것을 쓴다 (°C)
CLOTHING_BANDS = (
    (28, "매우 더워요. 민소매나 반팔, 반바지가 좋아요"),
    (23, "반팔이나 얇은 셔츠가 좋아요"),
    (17, "얇은 긴팔이나 가디건을 입으세요"),
    (12, "자켓이나 가디건을 챙기세요"),
    (5, "코트나 두꺼운 자켓을 입으세요"),
)
CLOTHING_COLDEST = "패딩이나 두꺼운 코트로 따뜻하게 입으세요"

# 미세먼지 등급 순위 (에어코리아 등급 이름 그대로)
GRADE_RANK = {"좋음": 0, "보통": 1, "나쁨": 2, "매우나쁨": 3}
DUST_UNKNOWN = "미세먼지는 확인하지 못했습니다"


def umbrella_advice(weather: dict) -> str | None:
    """지금 내리는 중이거나 예보 강수확률이 높을 때만 우산을 권한다. 낮으면 None."""
    rain_type = weather.get("precipitation_type")
    if rain_type and rain_type != "없음":
        return "지금 비나 눈이 오고 있어요. 우산을 챙기세요"
    prob = weather.get("precipitation_probability")
    if not isinstance(prob, (int, float)):
        return None
    if prob >= UMBRELLA_MUST:
        return "우산을 챙기세요"
    if prob >= UMBRELLA_MAYBE:
        return "비가 올 수 있으니 작은 우산이 있으면 좋아요"
    return None  # 비 올 가능성이 낮으면 말하지 않는다 (강수확률 수치는 문장에 따로 들어간다)


def clothing_advice(weather: dict) -> str | None:
    temp = weather.get("temperature_c")
    if not isinstance(temp, (int, float)):
        return None
    for lower, text in CLOTHING_BANDS:
        if temp >= lower:
            return text
    return CLOTHING_COLDEST


def _dust_ranks(air: dict) -> list[int]:
    """PM10·PM2.5 등급 중 알아볼 수 있는 것의 순위 목록. 모르면 빈 목록."""
    ranks = []
    for key in ("pm10_grade", "pm25_grade"):
        grade = air.get(key)
        if isinstance(grade, str):
            rank = GRADE_RANK.get(grade.replace(" ", ""))
            if rank is not None:
                ranks.append(rank)
    return ranks


def dust_advice(air: dict) -> str | None:
    """PM10·PM2.5 중 더 나쁜 등급이 '나쁨' 이상일 때만 안내한다 (보통 이하는 말하지 않는다)."""
    worst = max(_dust_ranks(air), default=0)
    if worst >= 3:
        return "미세먼지가 매우 나쁨이에요. 외출을 줄이고 마스크를 착용하세요"
    if worst == 2:
        return "미세먼지가 나쁨이에요. 마스크를 착용하세요"
    return None


def build_advice(data: dict) -> dict:
    """브리핑 데이터에서 안내를 모은다. 순서는 우산 > 옷차림 > 미세먼지, 말할 게 없는 항목은 뺀다."""
    weather = data.get("weather") if isinstance(data, dict) else None
    air = data.get("air") if isinstance(data, dict) else None
    advice = {}
    if isinstance(weather, dict):
        advice["umbrella"] = umbrella_advice(weather)
        advice["clothing"] = clothing_advice(weather)
    if isinstance(air, dict) and _dust_ranks(air):
        advice["dust"] = dust_advice(air)
    elif isinstance(weather, dict):
        advice["dust"] = DUST_UNKNOWN  # 날씨는 있는데 대기질을 못 가져온 경우만 알린다
    return {key: text for key, text in advice.items() if text}