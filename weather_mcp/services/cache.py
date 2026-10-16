"""간단한 메모리 TTL 캐시. 프로그램이 살아 있는 동안만 유지된다."""
import time


class TTLCache:
    """키별로 값을 저장하고, ttl_seconds가 지나면 만료시키는 캐시."""

    def __init__(self, ttl_seconds: float, clock=time.monotonic):
        self.ttl = ttl_seconds
        self._clock = clock  # 테스트에서 가짜 시계를 넣을 수 있게 분리
        self._data = {}  # key -> (만료 시각, 값, 수집 시각)

    def get(self, key):
        """유효하면 (값, 수집 시각)을, 없거나 만료됐으면 None을 반환한다."""
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, value, fetched_at = item
        if self._clock() >= expires_at:
            del self._data[key]  # 만료된 항목은 지운다
            return None
        return value, fetched_at

    def set(self, key, value, fetched_at):
        """값을 저장한다. fetched_at은 API에서 실제로 받은 시각이다."""
        self._data[key] = (self._clock() + self.ttl, value, fetched_at)

    def clear(self):
        """모든 항목을 지운다. (테스트 초기화용)"""
        self._data.clear()