from fastapi.testclient import TestClient

from app.main import app
from app.services.settings_svc import clamp_threshold


def test_clamp_threshold():
    assert clamp_threshold(0.3) == 0.50
    assert clamp_threshold(1.4) == 0.99
    assert clamp_threshold(0.847) == 0.85


def test_pages_render():
    with TestClient(app) as client:
        for path in ("/", "/review", "/review?status=auto_accepted", "/audit", "/pages/status-board", "/assets/1"):
            r = client.get(path)
            assert r.status_code == 200, path


def test_threshold_endpoint():
    with TestClient(app) as client:
        r = client.post("/settings/threshold", data={"threshold": "0.85"})
        assert r.status_code == 200
        assert 'id="board-root"' in r.text
