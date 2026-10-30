import pytest
from weather_mcp.env_check import find_missing_env, require_env


def test_누락과_빈값을_모두_찾는다(monkeypatch):
    monkeypatch.setenv("A_KEY", "값있음")
    monkeypatch.setenv("B_KEY", "   ")      # 공백만 있으면 없는 것으로 본다
    monkeypatch.delenv("C_KEY", raising=False)
    assert find_missing_env(["A_KEY", "B_KEY", "C_KEY"]) == ["B_KEY", "C_KEY"]


def test_예외_메시지에_이름만_있고_값은_없다(monkeypatch):
    monkeypatch.setenv("A_KEY", "비밀값123")
    monkeypatch.delenv("B_KEY", raising=False)
    with pytest.raises(RuntimeError) as e:
        require_env(["A_KEY", "B_KEY"])
    assert "B_KEY" in str(e.value)
    assert "비밀값123" not in str(e.value)   # 값 유출 방지 확인