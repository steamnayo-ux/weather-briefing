"""ai_briefing 테스트. AI 호출은 가짜 함수로 바꿔서 네트워크를 쓰지 않는다."""
from weather_mcp.services import ai_briefing

# 테스트용 가짜 데이터 (필드 이름은 테스트를 위해 임의로 정했다)
DATA = {
    "location": "서울 강남구",
    "weather": {"temperature": 18, "sky": "맑음", "source": "kma", "collected_at": "2026-10-16T09:20:00+09:00"},
    "air": {"pm10": 19, "pm25": 4, "source": "airkorea", "collected_at": "2026-10-16T09:24:02+09:00"},
    "warnings": [],
    "built_at": "2026-10-16T09:30:00+09:00",
}
TEXT_OK = "서울 강남구는 18도로 맑고, 미세먼지(PM10)는 19로 좋음 수준입니다. 초미세먼지(PM2.5)는 4입니다."
TEXT_BAD = "서울 강남구의 기온은 25도입니다."


def test_build_prompt_includes_data_and_rules():
    prompt = ai_briefing.build_prompt(DATA)
    assert "서울 강남구" in prompt
    assert '"pm10": 19' in prompt          # 데이터가 JSON으로 들어간다
    assert "데이터에 없는" in prompt        # 지어내지 말라는 규칙이 들어간다


def test_find_unsupported_numbers_flags_invented():
    assert ai_briefing.find_unsupported_numbers("기온 25도, 미세먼지 19", DATA) == ["25"]


def test_find_unsupported_numbers_ignores_pm_labels():
    # PM2.5 이름 속의 2.5는 데이터에 없어도 지어낸 숫자로 보지 않는다
    assert ai_briefing.find_unsupported_numbers(TEXT_OK, DATA) == []


def test_generate_success(monkeypatch):
    monkeypatch.setattr(ai_briefing.briefing, "build_briefing_data", lambda name: DATA)
    prompts = []

    def fake_caller(prompt):
        prompts.append(prompt)
        return TEXT_OK

    result = ai_briefing.generate_briefing("서울 강남구", caller=fake_caller)

    assert "error" not in result
    assert result["briefing"] == TEXT_OK
    assert result["data"] == DATA          # 근거 데이터가 함께 남는다
    assert len(prompts) == 1


def test_generate_rejects_invented_number(monkeypatch):
    monkeypatch.setattr(ai_briefing.briefing, "build_briefing_data", lambda name: DATA)
    result = ai_briefing.generate_briefing("서울 강남구", caller=lambda prompt: TEXT_BAD)

    assert "error" in result and "25" in result["error"]
    assert "briefing" not in result        # 잘못된 브리핑은 내보내지 않는다


def test_generate_ai_error(monkeypatch):
    monkeypatch.setattr(ai_briefing.briefing, "build_briefing_data", lambda name: DATA)



def test_generate_skips_ai_when_data_error(monkeypatch):
    monkeypatch.setattr(
        ai_briefing.briefing, "build_briefing_data",
        lambda name: {"error": "날씨와 대기질 정보를 모두 가져오지 못했습니다", "warnings": ["x"]},
    )
    calls = []
    result = ai_briefing.generate_briefing("서울 강남구", caller=lambda prompt: calls.append(prompt) or "텍스트")

    assert "error" in result
    assert calls == []                      # 데이터가 없으면 AI를 호출하지 않는다



def test_find_unsupported_numbers_ignores_key_names():
    # 키 이름(pm25)에 든 25 때문에 지어낸 25가 통과하면 안 된다
    data = {"air": {"pm25": 4}}
    assert ai_briefing.find_unsupported_numbers("초미세먼지 25", data) == ["25"]





def test_find_unsupported_numbers_allows_hour_from_time_fields():
    data = {"weather": {"observed_at": "20261016 1300", "forecast_for": "20261016 1500"}}
    # 13시, 15시, 오후 3시는 시각 값에서 나온 숫자라 허용한다
    assert ai_briefing.find_unsupported_numbers("13시 관측, 15시 예보, 오후 3시", data) == []


def test_find_unsupported_numbers_does_not_allow_seconds():
    data = {"weather": {"collected_at": "2026-10-16T14:07:13+09:00"}}
    # 초(13)는 허용하지 않는다. 우연히 같아서 통과하는 것을 막는다
    assert ai_briefing.find_unsupported_numbers("13시", data) == ["13"]


def test_kakao_prompt_requires_values_and_hides_process():
    prompt = ai_briefing.build_prompt({"location": "분당구"}, max_chars=150)
    assert "150자" in prompt
    assert "°C" in prompt and "dust" in prompt  # 미세먼지는 수치가 아니라 advice의 dust 안내로 말한다
    assert "처리 과정" in prompt   # 측정소 대체 같은 내부 과정을 말하지 않게 한다


def test_default_prompt_has_no_kakao_rules():
    prompt = ai_briefing.build_prompt({"location": "분당구"})
    assert "㎍/㎥" not in prompt