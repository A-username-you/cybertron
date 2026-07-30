from fastapi.testclient import TestClient
from cybertron.gateway import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["version"] == "3.0.0"

def test_config_safe():
    r = client.get("/config")
    assert r.status_code == 200
    assert r.json()["nim_api_key"] in ("", "***")

def test_personas():
    r = client.get("/personas")
    assert r.status_code == 200
    assert len(r.json()["personas"]) >= 5

def test_api_health():
    r = client.get("/api/")
    assert r.status_code == 200
