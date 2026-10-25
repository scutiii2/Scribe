from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.middleware import InternalTokenMiddleware


def client(token):
    app = Starlette(routes=[
        Route("/api/x", lambda r: PlainTextResponse("ok")),
        Route("/health", lambda r: PlainTextResponse("ok")),
    ])
    app.add_middleware(InternalTokenMiddleware, token=token)
    return TestClient(app)


def test_token_required_on_api_not_health():
    c = client("secret")
    assert c.get("/api/x").status_code == 401
    assert c.get("/api/x", headers={"X-Internal-Token": "wrong"}).status_code == 401
    assert c.get("/api/x", headers={"X-Internal-Token": "secret"}).status_code == 200
    assert c.get("/health").status_code == 200


def test_no_token_configured_allows_all():
    assert client("").get("/api/x").status_code == 200
