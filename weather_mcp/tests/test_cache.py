"""TTLCache 단위 테스트. 가짜 시계로 시간이 흐른 것처럼 만든다."""
from weather_mcp.services.cache import TTLCache


class FakeClock:
    """테스트용 시계. advance()로 시간을 앞으로 보낸다."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_returns_value_within_ttl():
    clock = FakeClock()
    cache = TTLCache(ttl_seconds=60, clock=clock)
    cache.set("k", "v", "2026-10-16T09:00:00+09:00")
    clock.advance(59)  # 아직 만료 전
    assert cache.get("k") == ("v", "2026-10-16T09:00:00+09:00")


def test_returns_none_after_ttl():
    clock = FakeClock()
    cache = TTLCache(ttl_seconds=60, clock=clock)
    cache.set("k", "v", "t")
    clock.advance(60)  # 딱 TTL만큼 지나면 만료
    assert cache.get("k") is None


def test_returns_none_for_missing_key():
    cache = TTLCache(ttl_seconds=60)
    assert cache.get("없는키") is None