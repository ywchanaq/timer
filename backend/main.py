import os
import sys
import random
import threading
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import time
import sqlite3
import uvicorn
import webview

# Initialize FastAPI App
app = FastAPI()

# Enable CORS for the frontend development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- BACKEND AUDIO ENGINE SETUP (Pygame Mixer) ---
# Pygame's mixer is the standard choice for compiled .exe files (via PyInstaller)
# as it packages cleanly and runs audio playback asynchronously.
AUDIO_ENGINE_AVAILABLE = False
try:
    import pygame
    pygame.mixer.init()
    AUDIO_ENGINE_AVAILABLE = True
    print("Backend audio playback engine initialized successfully (pygame).")
except ImportError:
    print("WARNING: 'pygame' is not installed. Backend direct audio playback will be disabled until installed.")
except Exception as e:
    print(f"WARNING: Could not initialize audio mixer: {str(e)}")

# Global in-memory variable to track if a file has been preloaded
PRELOADED_FILE_PATH = None


# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("timers.db")
    cursor = conn.cursor()
    # Timers presets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stored_timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL
        )
    """)
    # Configuration table for directory paths and other settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()


# --- PYDANTIC DATA MODELS ---
class TimerRequest(BaseModel):
    duration_seconds: int

class SaveTimerRequest(BaseModel):
    label: str
    duration_seconds: int

class FolderPathRequest(BaseModel):
    path: str


# --- API ENDPOINTS ---
@app.get("/api/status")
def read_status():
    """Simple API healthcheck endpoint."""
    return {"status": "ok", "message": "Timer API is running"}

@app.post("/api/timer/start")
def start_timer(request: TimerRequest):
    if request.duration_seconds <= 0:
        raise HTTPException(
            status_code=400, 
            detail="Duration must be greater than 0 seconds"
        )
    
    current_time = time.time()
    return {
        "status": "started",
        "duration": request.duration_seconds,
        "end_time": current_time + request.duration_seconds
    }

@app.post("/api/timers")
def save_timer(request: SaveTimerRequest):
    clean_label = request.label.strip()
    if not clean_label:
        raise HTTPException(status_code=400, detail="Label cannot be empty")
    if request.duration_seconds <= 0:
        raise HTTPException(status_code=400, detail="Duration must be greater than 0 seconds")
        
    conn = sqlite3.connect("timers.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO stored_timers (label, duration_seconds) VALUES (?, ?)",
        (clean_label, request.duration_seconds)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Timer stored successfully!"}


@app.get("/api/timers")
def get_timers():
    conn = sqlite3.connect("timers.db")
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    cursor.execute("SELECT id, label, duration_seconds FROM stored_timers ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


@app.delete("/api/timers/{timer_id}")
def delete_timer(timer_id: int):
    conn = sqlite3.connect("timers.db")
    cursor = conn.cursor()
    
    # Check if the timer exists
    cursor.execute("SELECT id FROM stored_timers WHERE id = ?", (timer_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Timer not found")
        
    cursor.execute("DELETE FROM stored_timers WHERE id = ?", (timer_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Timer {timer_id} deleted successfully"}

# --- BACKEND FOLDER STORAGE AND SELECTION ---
@app.get("/api/config/folder")
def get_stored_folder():
    """Retrieves the currently saved folder path from the database."""
    conn = sqlite3.connect("timers.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_config WHERE key = 'alert_folder_path'")
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"folder_path": row[0]}
    return {"folder_path": ""}

@app.post("/api/config/folder")
def save_folder_path(request: FolderPathRequest):
    """Manually saves or updates the folder path in the database."""
    clean_path = request.path.strip()
    conn = sqlite3.connect("timers.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO app_config (key, value) VALUES ('alert_folder_path', ?)",
        (clean_path,)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "folder_path": clean_path}

@app.post("/api/config/select-folder")
def select_folder_via_dialog():
    """
    Opens a native OS directory picker dialog using Python's built-in Tkinter.
    Saves the selected path directly into SQLite and returns it to the client.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        raise HTTPException(
            status_code=500, 
            detail="Tkinter is not installed or supported on this backend environment."
        )

    # Initialize a hidden Tkinter frame
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)  # Bring the directory dialog to front
    
    selected_path = filedialog.askdirectory(title="Select Alarm Audio Folder (MP3/WAV)")
    root.destroy()

    if not selected_path:
        # User cancelled the selection
        return {"status": "cancelled", "folder_path": ""}

    # Save to SQLite
    conn = sqlite3.connect("timers.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO app_config (key, value) VALUES ('alert_folder_path', ?)",
        (selected_path,)
    )
    conn.commit()
    conn.close()

    return {"status": "success", "folder_path": selected_path}

# --- BACKEND AUDIO CONTROL ENDPOINTS ---
@app.post("/api/alert/preload-backend")
def preload_alert_on_backend():
    """
    Finds a random .mp3 or .wav file in the configured directory and preloads
    it into the pygame mixer's memory buffer. This eliminates the latency when
    the countdown timer reaches zero.
    """
    global AUDIO_ENGINE_AVAILABLE, PRELOADED_FILE_PATH
    if not AUDIO_ENGINE_AVAILABLE:
        raise HTTPException(
            status_code=500, 
            detail="Backend audio engine (pygame) is not available. Please run: pip install pygame"
        )

    conn = sqlite3.connect("timers.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_config WHERE key = 'alert_folder_path'")
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0].strip():
        raise HTTPException(status_code=400, detail="No alert folder path configured in backend.")

    folder_path = row[0].strip()
    normalized_path = os.path.abspath(folder_path)
    
    if not os.path.exists(normalized_path) or not os.path.isdir(normalized_path):
        raise HTTPException(status_code=400, detail="Configured folder path does not exist on this machine.")

    # Scan for MP3s and WAVs
    media_extensions = ('.mp3', '.wav')
    try:
        media_files = [
            f for f in os.listdir(normalized_path) 
            if f.lower().endswith(media_extensions) and os.path.isfile(os.path.join(normalized_path, f))
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read folder directory: {str(e)}")

    if not media_files:
        raise HTTPException(
            status_code=404, 
            detail="No .mp3 or .wav files found in configured folder path."
        )

    # Choose a random file and preload it into the background player
    random_media = random.choice(media_files)
    full_file_path = os.path.join(normalized_path, random_media)

    try:
        pygame.mixer.music.load(full_file_path)
        PRELOADED_FILE_PATH = full_file_path
        return {
            "status": "preloaded", 
            "file": random_media, 
            "message": "Audio file loaded into memory buffer successfully."
        }
    except Exception as e:
        PRELOADED_FILE_PATH = None
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to preload audio file on backend: {str(e)}"
        )


@app.post("/api/alert/play-backend")
def play_alert_on_backend():
    """
    Plays the alarm. If a file was already preloaded, it starts playing 
    instantly (0ms delay). Otherwise, it fallback-loads a random audio file 
    and triggers playback.
    """
    global AUDIO_ENGINE_AVAILABLE, PRELOADED_FILE_PATH
    if not AUDIO_ENGINE_AVAILABLE:
        raise HTTPException(
            status_code=500, 
            detail="Backend audio engine (pygame) is not available. Please run: pip install pygame"
        )

    # If the file is already preloaded, trigger play instantly!
    if PRELOADED_FILE_PATH is not None:
        try:
            pygame.mixer.music.play(-1)  # -1 plays in an infinite loop
            file_name = os.path.basename(PRELOADED_FILE_PATH)
            PRELOADED_FILE_PATH = None  # Reset tracking state
            return {
                "status": "playing",
                "file": file_name,
                "message": "Instant playback triggered from memory buffer."
            }
        except Exception as e:
            PRELOADED_FILE_PATH = None  # Reset bad preloaded state
            print(f"Preloaded playback failed: {str(e)}, falling back to standard loading...")

    # Fallback/On-Demand Path if no preloading was completed
    conn = sqlite3.connect("timers.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_config WHERE key = 'alert_folder_path'")
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0].strip():
        raise HTTPException(status_code=400, detail="No alert folder path configured in backend.")

    folder_path = row[0].strip()
    normalized_path = os.path.abspath(folder_path)
    
    if not os.path.exists(normalized_path) or not os.path.isdir(normalized_path):
        raise HTTPException(status_code=400, detail="Configured folder path does not exist on this machine.")

    media_extensions = ('.mp3', '.wav')
    try:
        media_files = [
            f for f in os.listdir(normalized_path) 
            if f.lower().endswith(media_extensions) and os.path.isfile(os.path.join(normalized_path, f))
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read folder directory: {str(e)}")

    if not media_files:
        raise HTTPException(
            status_code=404, 
            detail="No .mp3 or .wav files found in configured folder path."
        )

    random_media = random.choice(media_files)
    full_file_path = os.path.join(normalized_path, random_media)

    try:
        pygame.mixer.music.load(full_file_path)
        pygame.mixer.music.play(-1)
        return {
            "status": "playing", 
            "file": random_media, 
            "message": "Fallback playback started (on-demand loading)."
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to play audio file on backend: {str(e)}"
        )


@app.post("/api/alert/stop-backend")
def stop_alert_on_backend():
    """Stops any active audio playback on the backend machine instantly."""
    global AUDIO_ENGINE_AVAILABLE, PRELOADED_FILE_PATH
    if not AUDIO_ENGINE_AVAILABLE:
        return {"status": "ignored", "message": "Backend audio engine is not installed."}

    try:
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()  # Release file lock immediately
        PRELOADED_FILE_PATH = None  # Reset preloaded states on manual stop
        return {"status": "stopped", "message": "Backend playback stopped successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to stop audio playback on backend: {str(e)}"
        )


# --- LEGACY STREAMING ENDPOINT (Optional Fallback) ---
@app.get("/api/alert/random")
def get_random_alert():
    """
    Saves bandwidth by falling back to streaming over HTTP if needed,
    scans for .mp3 or .wav files, and sends a random file to the browser.
    """
    conn = sqlite3.connect("timers.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM app_config WHERE key = 'alert_folder_path'")
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0].strip():
        raise HTTPException(status_code=400, detail="No alert folder path configured in backend.")

    folder_path = row[0].strip()
    normalized_path = os.path.abspath(folder_path)
    
    if not os.path.exists(normalized_path) or not os.path.isdir(normalized_path):
        raise HTTPException(status_code=400, detail="The configured folder path does not exist or is not a directory.")
        
    media_extensions = ('.mp3', '.wav')
    try:
        media_files = [
            f for f in os.listdir(normalized_path) 
            if f.lower().endswith(media_extensions) and os.path.isfile(os.path.join(normalized_path, f))
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read folder directory: {str(e)}")
    
    if not media_files:
        raise HTTPException(
            status_code=404, 
            detail="No .mp3 or .wav files found in directory."
        )
        
    random_media = random.choice(media_files)
    full_file_path = os.path.join(normalized_path, random_media)
    
    # Determine correct audio MIME Type dynamically
    mime_type = "audio/mpeg" if random_media.lower().endswith('.mp3') else "audio/wav"
    
    return FileResponse(full_file_path, media_type=mime_type)

# --- MOUNT STATIC ASSETS (VUE FRONTEND) ---
# Resolve the path to the 'dist' folder generated by npm run build
if getattr(sys, 'frozen', False):
    # Running inside PyInstaller environment
    base_path = sys._MEIPASS
else:
    # Running directly in normal interpreter mode
    base_path = os.path.dirname(os.path.abspath(__file__))

static_dir = os.path.join(base_path, 'dist')

# Serve compiled frontend assets directly from root.
# Make sure "npm run build" output matches this "dist" structure.
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    print(f"WARNING: Static files folder '{static_dir}' was not found. Native frontend will not render.")


# --- THREADING AND LIFECYCLE MANAGEMENT ---
def start_fastapi():
    """Worker target running the ASGI server inside a daemonized background thread."""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    # 1. Start the FastAPI backend inside a background thread
    server_thread = threading.Thread(target=start_fastapi, daemon=True)
    server_thread.start()
    
    # 2. Spawn a native desktop GUI frame directing to the running server
    # Configured to look like a clean, responsive desktop interface card
    webview.create_window(
        title="⏱️ Custom PyGame Timer App",
        url="http://127.0.0.1:8000",
        width=1000,
        height=750,
        resizable=True
    )
    
    # 3. Enter the main graphical window loop to prevent python from exiting
    webview.start()