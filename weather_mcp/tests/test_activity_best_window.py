"""find_best_window(좋은 시간대 계산) 테스트. 네트워크를 쓰지 않는다."""
from weather_mcp.services.activity import find_best_window


def hour(h, ptype="없음", pop=0, humidity=50, wind=1.0, temp=15.0):
    """테스트용 시간별 예보 한 칸."""
    return {
        "time": f"{h:02d}:00",
        "precipitation_type": ptype,
        "precipitation_probability": pop,
        "humidity_pct": humidity,
        "wind_speed_ms": wind,
        "temperature_c": temp,
    }


def hours(start, end, **kw):
    return [hour(h, **kw) for h in range(start, end + 1)]


def test_모두_괜찮으면_전체_구간():
    assert find_best_window(hours(9, 18), "빨래") == {"start": "09:00", "end": "18:00", "hours": 10}


def test_비_오는_시각을_빼고_가장_긴_구간을_고른다():
    data = hours(9, 11) + [hour(12, ptype="비", pop=80)] + hours(13, 18)
    # 9~11(3시간) vs 13~18(6시간)
    assert find_best_window(data, "외출") == {"start": "13:00", "end": "18:00", "hours": 6}


def test_길이가_같으면_이른_구간():
    data = hours(9, 12) + [hour(13, ptype="비")] + hours(14, 17)
    assert find_best_window(data, "산책") == {"start": "09:00", "end": "12:00", "hours": 4}


def test_지난_시각은_제외한다():
    # 지금이 14시면 9~13시는 후보가 아니다
    assert find_best_window(hours(9, 18), "빨래", min_hour=14) == {"start": "14:00", "end": "18:00", "hours": 5}


def test_강수확률이_기준_이상이면_제외():
    data = hours(9, 11) + [hour(12, pop=30)] + hours(13, 14)
    assert find_best_window(data, "외출") == {"start": "09:00", "end": "11:00", "hours": 3}


def test_빨래는_습도가_높은_시각을_제외():
    data = hours(9, 10, humidity=90) + hours(11, 16, humidity=40)
    assert find_best_window(data, "빨래") == {"start": "11:00", "end": "16:00", "hours": 6}


def test_러닝은_바람과_더위도_본다():
    data = hours(6, 8, wind=9.0) + hours(9, 10, temp=30.0) + hours(11, 13)
    assert find_best_window(data, "러닝") == {"start": "11:00", "end": "13:00", "hours": 3}


def test_외출은_습도와_바람을_보지_않는다():
    assert find_best_window(hours(9, 12, humidity=95, wind=12.0, temp=35.0), "외출") is not None


def test_괜찮은_시각이_없으면_None():
    assert find_best_window(hours(9, 12, ptype="비"), "러닝") is None


def test_빈_목록과_지난_시각만_있으면_None():
    assert find_best_window([], "빨래") is None
    assert find_best_window(hours(9, 12), "빨래", min_hour=20) is None


def test_모르는_값은_규칙을_적용하지_않는다():
    data = [{"time": f"{h:02d}:00"} for h in range(9, 12)]
    assert find_best_window(data, "러닝") == {"start": "09:00", "end": "11:00", "hours": 3}


def test_시각이_끊기면_다른_구간():
    # 10시 다음이 12시: 시간이 이어지지 않으므로 한 구간으로 합치지 않는다
    data = [hour(9), hour(10), hour(12), hour(13), hour(14)]
    assert find_best_window(data, "산책") == {"start": "12:00", "end": "14:00", "hours": 3}