import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from weather_mcp.remote_auth import (
    ApiKeyMiddleware, RemoteAuthConfigError, load_remote_key,
)

KEY = "k" * 40


@pytest.fixture
def client():
    async def mcp_stub(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/mcp", mcp_stub)])
    return TestClient(ApiKeyMiddleware(app, KEY))


def test_키_없으면_401(client):
    assert client.get("/mcp").status_code == 401


def test_틀린_키는_401(client):
    assert client.get("/mcp", headers={"x-api-key": "x" * 40}).status_code == 401


def test_빈_쿼리_키는_401(client):
    assert client.get("/mcp?key=").status_code == 401


def test_x_api_key_헤더_통과(client):
    assert client.get("/mcp", headers={"x-api-key": KEY}).status_code == 200


def test_bearer_헤더_통과(client):
    assert client.get("/mcp", headers={"Authorization": f"Bearer {KEY}"}).status_code == 200


def test_쿼리_키_통과(client):
    assert client.get(f"/mcp?key={KEY}").status_code == 200


def test_틀린_쿼리_키는_401(client):
    assert client.get("/mcp?key=wrong").status_code == 401


def test_health는_키_없이_통과(client):
    assert client.get("/health").status_code == 200


def test_401_응답에_키가_들어가지_않음(client):
    r = client.get(f"/mcp?key={'z' * 40}")
    assert r.status_code == 401
    assert KEY not in r.text and "z" * 40 not in r.text


def test_키_설정_없으면_예외():
    with pytest.raises(RemoteAuthConfigError):
        load_remote_key({})


def test_짧은_키는_예외():
    with pytest.raises(RemoteAuthConfigError):
        load_remote_key({"REMOTE_API_KEY": "short"})


def test_충분한_키는_통과():
    assert load_remote_key({"REMOTE_API_KEY": KEY}) == KEY