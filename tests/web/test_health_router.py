from fastapi.testclient import TestClient

from mercari_alert_bot.web.app import create_web_app
from tests.web.test_app import RecordingLifespan


def test_healthz_returns_ok() -> None:
    with TestClient(create_web_app(RecordingLifespan())) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_needs_no_wired_service() -> None:
    app = create_web_app(RecordingLifespan())

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert app.dependency_overrides == {}
    assert response.status_code == 200


def test_healthz_is_not_shadowed_by_static_mount() -> None:
    with TestClient(create_web_app(RecordingLifespan())) as client:
        response = client.get("/healthz")

    assert response.headers["content-type"].startswith("application/json")
