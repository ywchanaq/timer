from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "Timer API is running"}

def test_start_timer_success():
    # Test valid input
    response = client.post("/api/timer/start", json={"duration_seconds": 60})
    assert response.status_code == 200
    assert response.json()["status"] == "started"
    assert response.json()["duration"] == 60
    assert "end_time" in response.json()

def test_start_timer_invalid():
    # Test validation error (negative time)
    response = client.post("/api/timer/start", json={"duration_seconds": -10})
    assert response.status_code == 400
    assert response.json()["detail"] == "Duration must be greater than 0 seconds"