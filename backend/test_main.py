import os
import pytest
import sqlite3
from fastapi.testclient import TestClient

# Use a separate database file for tests to prevent pollution of production data
TEST_DB_PATH = "test_timers.db"

@pytest.fixture(autouse=True)
def setup_and_teardown_db(monkeypatch):
    """
    Sets up a clean test database schema before every test and cleans it up after.
    """
    # Remove any stale test database
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

    # Create the schema in the test database
    conn = sqlite3.connect(TEST_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stored_timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

    # Monkeypatch sqlite3.connect inside main to direct queries to our test database
    original_connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda db_name: original_connect(TEST_DB_PATH))

    yield

    # Clean up test database file after the test completes
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass


# Import TestClient with our monkeypatched main module
from main import app
client = TestClient(app)


# --- Existing Route Tests ---

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "Timer API is running"}


def test_start_timer_success():
    response = client.post("/api/timer/start", json={"duration_seconds": 60})
    assert response.status_code == 200
    assert response.json()["status"] == "started"
    assert response.json()["duration"] == 60
    assert "end_time" in response.json()


def test_start_timer_invalid():
    response = client.post("/api/timer/start", json={"duration_seconds": -10})
    assert response.status_code == 400
    assert response.json()["detail"] == "Duration must be greater than 0 seconds"


# --- New Stored Preset Tests ---

def test_save_timer_preset_success():
    """Verify that a valid preset is saved successfully."""
    payload = {"label": "Pomodoro Focus", "duration_seconds": 1500}
    response = client.post("/api/timers", json=payload)
    
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Timer stored successfully!"}


def test_save_timer_preset_empty_label():
    """Verify that saving an empty or whitespace-only label yields a 400."""
    payload = {"label": "   ", "duration_seconds": 1500}
    response = client.post("/api/timers", json=payload)
    
    assert response.status_code == 400
    assert "Label cannot be empty" in response.json()["detail"]


def test_save_timer_preset_invalid_duration():
    """Verify that saving a non-positive duration is rejected."""
    payload = {"label": "Quick Break", "duration_seconds": 0}
    response = client.post("/api/timers", json=payload)
    
    assert response.status_code == 400
    assert "greater than 0" in response.json()["detail"]


def test_get_timers_ordered():
    """Verify that we can retrieve saved presets sorted by newest first."""
    # Seed presets
    client.post("/api/timers", json={"label": "Short Break", "duration_seconds": 300})
    client.post("/api/timers", json={"label": "Long Break", "duration_seconds": 900})

    response = client.get("/api/timers")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 2
    # Since they are ordered DESC by id, "Long Break" (second insert) should be first
    assert data[0]["label"] == "Long Break"
    assert data[1]["label"] == "Short Break"


def test_delete_timer_success():
    """Verify that a stored timer can be successfully deleted."""
    # Seed a preset
    client.post("/api/timers", json={"label": "Delete Me", "duration_seconds": 60})
    timers = client.get("/api/timers").json()
    target_id = timers[0]["id"]

    # Delete the preset
    response = client.delete(f"/api/timers/{target_id}")
    assert response.status_code == 200
    assert "deleted successfully" in response.json()["message"]

    # Confirm it is no longer returned
    remaining = client.get("/api/timers").json()
    assert len(remaining) == 0


def test_delete_timer_not_found():
    """Verify that attempting to delete a non-existent preset returns a 404."""
    response = client.delete("/api/timers/99999")
    assert response.status_code == 404
    assert "Timer not found" in response.json()["detail"]