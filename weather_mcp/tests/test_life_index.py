"""생활지수 규칙 테스트. 네트워크는 쓰지 않는다."""
import re

import pytest

from weather_mcp.services import ai_briefing, life_index


def w(temp=15, prob=0, rain="없음"):
    return {"temperature_c": temp, "precipitation_probability": prob, "precipitation_type": rain}


def test_umbrella_by_probability():
    assert life_index.umbrella_advice(w(prob=10)) is None  # 낮으면 아예 말하지 않는다
    assert "작은 우산" in life_index.umbrella_advice(w(prob=30))
    assert life_index.umbrella_advice(w(prob=60)) == "우산을 챙기세요"


def test_umbrella_when_raining_now_ignores_low_probability():
    assert "우산을 챙기세요" in life_index.umbrella_advice(w(prob=0, rain="비"))


def test_umbrella_unknown_probability_gives_nothing():
    assert life_index.umbrella_advice({"precipitation_type": "없음"}) is None


@pytest.mark.parametrize("temp, keyword", [
    (30, "반팔"), (28, "반팔"), (25, "반팔"),
    (20, "가디건"), (13.6, "자켓"), (12, "자켓"),
    (8, "코트"), (5, "코트"), (4.9, "패딩"), (-3, "패딩"),
])
def test_clothing_bands(temp, keyword):
    assert keyword in life_index.clothing_advice(w(temp=temp))


def test_clothing_unknown_temperature_gives_nothing():
    assert life_index.clothing_advice({"temperature_c": None}) is None


@pytest.mark.parametrize("pm10, pm25, expected", [
    ("좋음", "보통", None),
    ("보통", "보통", None),
    ("보통", "나쁨", "마스크"),              # 둘 중 더 나쁜 쪽 기준
    ("매우 나쁨", "보통", "외출을 줄이고"),   # 띄어쓰기가 있어도 인식
    (None, None, None),
])
def test_dust_uses_worse_grade(pm10, pm25, expected):
    result = life_index.dust_advice({"pm10_grade": pm10, "pm25_grade": pm25})
    if expected is None:
        assert result is None
    else:
        assert expected in result


def test_build_advice_order_and_missing_parts():
    data = {"weather": w(temp=13.6, prob=0), "air": {"pm10_grade": "나쁨"}}
    assert list(life_index.build_advice(data)) == ["clothing", "dust"]  # 비 안 오면 우산 항목 없음
    assert life_index.build_advice({"weather": None, "air": None}) == {}
    assert life_index.build_advice({}) == {}


def test_rainy_day_puts_umbrella_first():
    data = {"weather": w(temp=13.6, prob=80), "air": {"pm10_grade": "좋음"}}
    assert list(life_index.build_advice(data)) == ["umbrella", "clothing"]


def test_good_or_normal_dust_is_not_mentioned():
    data = {"weather": w(), "air": {"pm10_grade": "보통", "pm25_grade": "좋음"}}
    assert "dust" not in life_index.build_advice(data)


def test_unknown_dust_is_reported_only_when_weather_exists():
    with_weather = life_index.build_advice({"weather": w(), "air": None})
    assert with_weather["dust"] == life_index.DUST_UNKNOWN
    assert life_index.build_advice({"weather": None, "air": None}) == {}


def test_advice_text_has_no_digits():
    # 숫자가 들어가면 AI 문장의 '데이터에 없는 숫자' 검사와 충돌할 수 있다
    texts = [t for _, t in life_index.CLOTHING_BANDS]
    texts += [life_index.CLOTHING_COLDEST, life_index.DUST_UNKNOWN]
    for temp in range(-10, 40):
        data = {"weather": w(temp=temp, prob=temp * 3), "air": {"pm10_grade": "매우나쁨"}}
        texts += life_index.build_advice(data).values()
    assert not any(re.search(r"\d", t) for t in texts)


def test_prompt_includes_advice_only_for_kakao():
    data = {"location": "분당구", "weather": w(temp=13.6), "air": None, "warnings": []}
    assert '"advice"' in ai_briefing.build_prompt(data, max_chars=150)
    assert '"advice"' not in ai_briefing.build_prompt(data)