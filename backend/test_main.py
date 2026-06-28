import os
import pytest
import sqlite3
import tempfile
import sys
from unittest.mock import MagicMock

# Create a fake pystray module and inject it into sys.modules
mock_pystray = MagicMock()
sys.modules['pystray'] = mock_pystray
sys.modules['pystray._win32'] = MagicMock() # To prevent the line 22 crash

import main  # Import the main module to cleanly mock and reset global state
from fastapi.testclient import TestClient

# Use a separate database file for tests to prevent pollution of production data
TEST_DB_PATH = "test_timers.db"

@pytest.fixture(autouse=True)
def setup_and_teardown_db(monkeypatch):
    """
    Sets up a clean test database schema before every test and cleans it up after.
    It builds both presets and system configuration tables, clears stale rows,
    and resets/mocks global audio state to prevent cross-test pollution.
    """
    # Create the schema if it doesn't exist
    conn = sqlite3.connect(TEST_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stored_timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    
    # CLEAR DATA BEFORE EACH TEST TO PREVENT POLLUTION
    cursor.execute("DELETE FROM stored_timers")
    cursor.execute("DELETE FROM app_config")
    conn.commit()
    conn.close()

    # Monkeypatch sqlite3.connect inside main to direct queries to our test database
    original_connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda db_name: original_connect(TEST_DB_PATH))

    # Reset global timer variables in the main module to guarantee isolation between tests
    monkeypatch.setattr(main, "PRELOADED_FILE_PATH", None)

    # Completely mock pygame to protect test runs from missing local audio configurations or packages
    class MockMusic:
        def load(self, path): pass
        def play(self, loops=-1): pass
        def stop(self): pass
        def unload(self): pass

    class MockMixer:
        music = MockMusic()
        def init(self): pass

    class MockPygame:
        mixer = MockMixer()

    monkeypatch.setattr(main, "pygame", MockPygame(), raising=False)
    monkeypatch.setattr(main, "AUDIO_ENGINE_AVAILABLE", True)

    yield

    # Clean up data after the test completes (optional but good practice)
    try:
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stored_timers")
        cursor.execute("DELETE FROM app_config")
        conn.commit()
        conn.close()
    except Exception:
        pass


# Import TestClient with our monkeypatched main module
from main import app
client = TestClient(app)


# --- Existing Route Tests ---

def test_read_root():
    response = client.get("/api/status")
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


# --- New App Configuration Endpoints Tests ---

def test_get_stored_folder_empty():
    """Verify that configuration initially returns an empty directory path."""
    response = client.get("/api/config/folder")
    assert response.status_code == 200
    assert response.json() == {"folder_path": ""}


def test_save_and_retrieve_folder_path():
    """Verify that we can save a custom directory path and then fetch it."""
    payload = {"path": "/var/mock/alarms"}
    save_res = client.post("/api/config/folder", json=payload)
    assert save_res.status_code == 200
    assert save_res.json()["folder_path"] == "/var/mock/alarms"

    get_res = client.get("/api/config/folder")
    assert get_res.status_code == 200
    assert get_res.json() == {"folder_path": "/var/mock/alarms"}


# --- New Audio & Media Sandbox Endpoint Tests ---

@pytest.fixture
def temp_audio_sandbox():
    """Creates a temporary test directory populated with fake audio files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a mock .mp3 and .wav file inside
        with open(os.path.join(temp_dir, "test_bell.mp3"), "wb") as f:
            f.write(b"MOCK MP3 DATA")
        with open(os.path.join(temp_dir, "test_siren.wav"), "wb") as f:
            f.write(b"MOCK WAV DATA")
        # Create an unrelated non-media file (should be ignored)
        with open(os.path.join(temp_dir, "ignore_me.txt"), "w") as f:
            f.write("text data")
        yield temp_dir


def test_preload_alert_invalid_scenarios():
    """Tests preload error feedback when no folder path config exists or directory is missing."""
    # 1. No folder configured
    res_no_config = client.post("/api/alert/preload-backend")
    assert res_no_config.status_code == 400
    assert "No alert folder path configured" in res_no_config.json()["detail"]

    # 2. Folder does not exist
    client.post("/api/config/folder", json={"path": "/this/path/does/not/exist/on/earth"})
    res_missing_folder = client.post("/api/alert/preload-backend")
    assert res_missing_folder.status_code == 400
    assert "does not exist" in res_missing_folder.json()["detail"]


def test_preload_alert_success(temp_audio_sandbox, monkeypatch):
    """Tests successful random audio preloading using a local file sandbox."""
    # Seed configuration with temp sandbox directory
    client.post("/api/config/folder", json={"path": temp_audio_sandbox})

    # Mock pygame loading behavior to avoid system sound crashes
    monkeypatch.setattr(main.pygame.mixer.music, "load", lambda path: None)

    response = client.post("/api/alert/preload-backend")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "preloaded"
    # Verify that it picked one of our mock audio files
    assert data["file"] in ["test_bell.mp3", "test_siren.wav"]


def test_play_alert_sequence(temp_audio_sandbox, monkeypatch):
    """Verifies standard playback flow (including infinite loop activation and reset/stops)."""
    client.post("/api/config/folder", json={"path": temp_audio_sandbox})

    # Mock all Pygame playback calls directly on the module-level mock to verify executions
    load_calls = []
    play_calls = []
    stop_calls = []
    unload_calls = []

    monkeypatch.setattr(main.pygame.mixer.music, "load", lambda path: load_calls.append(path))
    monkeypatch.setattr(main.pygame.mixer.music, "play", lambda loops: play_calls.append(loops))
    monkeypatch.setattr(main.pygame.mixer.music, "stop", lambda: stop_calls.append(True))
    monkeypatch.setattr(main.pygame.mixer.music, "unload", lambda: unload_calls.append(True))

    # Test direct playback without preloading
    play_res = client.post("/api/alert/play-backend")
    assert play_res.status_code == 200
    assert play_res.json()["status"] == "playing"
    assert len(load_calls) == 1
    assert play_calls == [-1]  # Loop endlessly

    # Test stopping playback
    stop_res = client.post("/api/alert/stop-backend")
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"
    assert len(stop_calls) == 1
    assert len(unload_calls) == 1


def test_streaming_fallback_alert(temp_audio_sandbox):
    """Verifies browser-side download fallback (streams files over HTTP with proper MIME types)."""
    client.post("/api/config/folder", json={"path": temp_audio_sandbox})

    response = client.get("/api/alert/random")
    assert response.status_code == 200
    assert response.headers["content-type"] in ["audio/mpeg", "audio/wav"]
