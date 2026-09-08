from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:  # context manager triggers lifespan → create_all
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["db"] == "up"


def test_index_renders():
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "TEMPNAME" in r.text
