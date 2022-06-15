from fastapi.testclient import TestClient

from etelemetry_app.server.app import app

client = TestClient(app)


def test_server_startup_shutdown():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["package"] == "etelemetry"
