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
import subprocess
import urllib.request  # Standard library utility for safe loopback API calling
from plyer import notification  # Native system notification utility

# PyInstaller Hidden Imports Guard
# This forces PyInstaller to bundle pystray's Windows backend files during compilation
TRAY_IMPORT_ERROR = None
try:
    import pystray._win32
except ImportError as e:
    TRAY_IMPORT_ERROR = str(e)

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

# --- Global Window and System Tray References ---
# Track the pywebview window instance, allowing the API and system tray to control window state
window = None
TRAY_AVAILABLE = False
tray_icon_instance = None

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
    with sqlite3.connect("timers.db") as conn:
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
        conn.commit()

init_db()


# --- NATIVE JS API BRIDGE (Direct Window-bound IPC) ---
class ApiBridge:
    def select_folder_dialog(self):
        """
        Invoked directly from frontend via window.pywebview.api.select_folder_dialog()
        Bypasses HTTP/TCP socket routing entirely for modern, secure desktop interaction.
        """
        global window
        if not window:
            return {"status": "error", "message": "Window context not found"}
            
        # Call native pywebview window frame explorer directory picker
        selected_folders = window.create_file_dialog(webview.FOLDER_DIALOG)
        
        if not selected_folders:
            return {"status": "cancelled", "folder_path": ""}
            
        selected_path = selected_folders[0]
        
        # Safely store straight into DB using a context manager
        with sqlite3.connect("timers.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES ('alert_folder_path', ?)",
                (selected_path,)
            )
            conn.commit()
            
        return {"status": "success", "folder_path": selected_path}


# --- PYDANTIC DATA MODELS ---
class TimerRequest(BaseModel):
    duration_seconds: int

class SaveTimerRequest(BaseModel):
    label: str
    duration_seconds: int

class FolderPathRequest(BaseModel):
    path: str


# --- Fallback: Native PowerShell Windows Notification ---
def send_powershell_notification(title, message):
    """
    Triggers a native Windows Toast notification using an asynchronous PowerShell subprocess.
    This acts as a 100% reliable click-interactive fallback inside PyInstaller-packaged executables.
    When clicked, it sends a REST call back to the local API server to restore the hidden window.
    """
    powershell_cmd = f"""
    [void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
    $objTrayIcon = New-Object System.Windows.Forms.NotifyIcon
    $objTrayIcon.Icon = [System.Drawing.SystemIcons]::Information
    $objTrayIcon.BalloonTipText = "{message}"
    $objTrayIcon.BalloonTipTitle = "{title}"
    $objTrayIcon.Visible = $True
    
    # Register click event handler to fire HTTP REST restore command back to our FastAPI process
    Register-ObjectEvent $objTrayIcon BalloonTipClicked BalloonClicked_event -Action {{
        try {{
            Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/window/restore" -Method Post
        }} catch {{}}
    }}
    
    $objTrayIcon.ShowBalloonTip(30000)
    
    # Wait for the user to click the notification or let it time out (extended to 30 seconds)
    Wait-Event -SourceIdentifier BalloonClicked_event -Timeout 30
    
    # Cleanup the object reference
    Unregister-Event -SourceIdentifier BalloonClicked_event -ErrorAction SilentlyContinue
    $objTrayIcon.Dispose()
    """
    try:
        # Launch PowerShell with a hidden console window to avoid flickering
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.Popen(
            ["powershell", "-Command", powershell_cmd],
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        print("Clickable PowerShell notification dispatched.")
    except Exception:
        print(f"PowerShell notification fallback failed: {str(e)}")


# --- Helper Function: Trigger System Popup, Notification, and Window Restore ---
def trigger_alert_popup():
    """
    Triggers native OS notification popup.
    On Windows, we explicitly bypass tray/plyer notifications and use PowerShell
    directly to guarantee that clicking the notification restores the window.
    """
    global window, TRAY_AVAILABLE, tray_icon_instance

    title = "⏱️ 時間到囉！"
    message = "您的倒數計時已經完成！點擊此處開啟主畫面。"

    # 1. On Windows, always prioritize PowerShell interactive notification
    if sys.platform == "win32":
        send_powershell_notification(title, message)
        return

    # 2. Non-Windows Tray Handler fallback
    if TRAY_AVAILABLE and tray_icon_instance:
        try:
            tray_icon_instance.notify(
                message=message,
                title=title
            )
            return
        except Exception as e:
            print(f"Failed to send tray notification: {str(e)}")
            
    # 3. Non-Windows Plyer Handler fallback
    try:
        notification.notify(
            title=title,
            message="您的倒數計時已經完成！",
            app_name="自訂計時器",
            timeout=10
        )
        return
    except Exception as e:
        print(f"Plyer notification failed: {str(e)}")


# --- System Tray Setup ---
def create_tray_icon_image():
    """
    Uses Pillow (PIL) to dynamically draw a clean, simple clock icon for the system tray.
    """
    try:
        from PIL import Image, ImageDraw
        # Create a canvas with transparent background
        image = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        # Draw blue circular outer border and clock face
        draw.ellipse((8, 8, 56, 56), fill=(59, 130, 246, 255), outline=(255, 255, 255, 255), width=4)
        # Draw clock hands (pointing to 2:00)
        draw.line((32, 32, 32, 18), fill=(255, 255, 255, 255), width=4)
        draw.line((32, 32, 46, 32), fill=(255, 255, 255, 255), width=4)
        return image
    except Exception as e:
        print(f"Failed to draw system tray icon: {str(e)}")
        return None

def setup_system_tray():
    """
    Initializes the system tray icon in the taskbar.
    """
    global TRAY_AVAILABLE, tray_icon_instance, TRAY_IMPORT_ERROR
    try:
        import pystray
        
        icon_image = create_tray_icon_image()
        if not icon_image:
            return
            
        def on_show_window(icon, item):
            try:
                # Thread-safe loopback API request to wake up and restore the main window
                req = urllib.request.Request("http://127.0.0.1:8000/api/window/restore", method="POST")
                urllib.request.urlopen(req)
            except Exception as e:
                print(f"Failed to trigger window restore from tray click: {str(e)}")
                
        def on_exit_app(icon, item):
            icon.stop()
            if window:
                try:
                    window.destroy()
                except Exception:
                    pass
            os._exit(0)
            
        # Define right-click context menu
        menu = pystray.Menu(
            pystray.MenuItem("開啟主畫面", on_show_window, default=True),
            pystray.MenuItem("結束程式", on_exit_app)
        )
        
        tray_icon_instance = pystray.Icon("TimerApp", icon_image, "自訂計時器", menu)
        TRAY_AVAILABLE = True
        
        # Start system tray loop in a background daemon thread to avoid blocking main thread UI
        tray_thread = threading.Thread(target=tray_icon_instance.run, daemon=True)
        tray_thread.start()
        print("System Tray support is enabled.")
    except ImportError as e:
        TRAY_IMPORT_ERROR = str(e)
        print("INFO: 'pystray' or 'Pillow' is not installed. Minimizing to system tray is disabled.")
        print("To enable, run: pip install pystray Pillow")
    except Exception as e:
        TRAY_IMPORT_ERROR = str(e)
        print(f"Failed to enable system tray: {str(e)}")

def on_window_closing():
    """
    Intercepts window close events. If system tray is active, hides the window 
    (maintaining background timer executions) instead of quitting the process.
    """
    global TRAY_AVAILABLE
    if TRAY_AVAILABLE:
        if window:
            window.hide()  # Hide window to tray
            # Send status notification using PowerShell to ensure click-interactive window recovery
            send_powershell_notification("⏱️ 計時器仍在運行", "應用程式已最小化至系統工作列，計時器仍會在背景為您讀秒！")
        return False  # Prevent window destruction
    return True  # Proceed with normal closing if tray is unavailable


# --- API Endpoints ---
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
        
    with sqlite3.connect("timers.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO stored_timers (label, duration_seconds) VALUES (?, ?)",
            (clean_label, request.duration_seconds)
        )
        conn.commit()
    return {"status": "success", "message": "Timer stored successfully!"}


@app.get("/api/timers")
def get_timers():
    with sqlite3.connect("timers.db") as conn:
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        cursor.execute("SELECT id, label, duration_seconds FROM stored_timers ORDER BY id DESC")
        rows = cursor.fetchall()
    
    return [dict(row) for row in rows]


@app.delete("/api/timers/{timer_id}")
def delete_timer(timer_id: int):
    with sqlite3.connect("timers.db") as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stored_timers WHERE id = ?", (timer_id,))
        conn.commit()
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Timer not found")
            
    return {"status": "success", "message": f"Timer {timer_id} deleted successfully"}

@app.get("/api/config/folder")
def get_stored_folder():
    with sqlite3.connect("timers.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_config WHERE key = 'alert_folder_path'")
        row = cursor.fetchone()
    
    return {"folder_path": row[0] if row else ""}

@app.post("/api/config/folder")
def save_folder_path(request: FolderPathRequest):
    clean_path = request.path.strip()
    with sqlite3.connect("timers.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES ('alert_folder_path', ?)",
            (clean_path,)
        )
        conn.commit()
    return {"status": "success", "folder_path": clean_path}


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

    with sqlite3.connect("timers.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_config WHERE key = 'alert_folder_path'")
        row = cursor.fetchone()

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
    and triggers playback. Also restores/focuses app window and fires native notification.
    """
    global AUDIO_ENGINE_AVAILABLE, PRELOADED_FILE_PATH
    if not AUDIO_ENGINE_AVAILABLE:
        raise HTTPException(
            status_code=500, 
            detail="Backend audio engine (pygame) is not available. Please run: pip install pygame"
        )

    # 1. Trigger native OS system notification (user clicks it to pop open the window)
    trigger_alert_popup()

    # 2. If the file is already preloaded, trigger play instantly!
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


@app.get("/api/diagnostic/tray")
def get_tray_diagnostics():
    """
    Diagnostic endpoint to determine if pystray/Pillow modules failed to bundle
    successfully during PyInstaller compilation. Helpful for tracking missing package dependencies.
    """
    global TRAY_AVAILABLE, TRAY_IMPORT_ERROR
    
    pystray_installed = False
    pillow_installed = False
    details = ""
    
    try:
        import pystray
        pystray_installed = True
    except Exception as e:
        details += f"[pystray error: {str(e)}] "
        
    try:
        from PIL import Image
        pillow_installed = True
    except Exception as e:
        details += f"[Pillow/PIL error: {str(e)}] "
        
    return {
        "system_tray_active": TRAY_AVAILABLE,
        "pystray_imported_successfully": pystray_installed,
        "pillow_imported_successfully": pillow_installed,
        "import_failure_reason": TRAY_IMPORT_ERROR or details or "None"
    }

@app.post("/api/window/minimize")
def trigger_window_minimize():
    """
    Exposed test route that allows the frontend interface to instantly test
    minimize-to-tray execution on command without needing to click the 'X' button.
    """
    global window, TRAY_AVAILABLE
    if window:
        try:
            if TRAY_AVAILABLE:
                window.hide()
                send_powershell_notification("⏱️ 計時器仍在運行", "已成功最小化至系統工作列，點擊此處還原！")
                return {"status": "success", "message": "Hidden to system tray successfully."}
            else:
                window.minimize()  # Normal taskbar minimize
                return {"status": "fallback", "message": "System tray unavailable. Fallback to normal minimize."}
        except Exception as e:
            return {"status": "error", "message": f"Minimization trigger failed: {str(e)}"}
    return {"status": "error", "message": "No active window handle found."}

@app.post("/api/window/restore")
def restore_window():
    """
    API endpoint specifically exposed to allow external processes (like PowerShell notifications
    or system tray clicks) to safely wake, restore, and focus our packaged pywebview application window.
    """
    global window
    if window:
        try:
            window.show()
            window.restore()
            window.focus()
            return {"status": "success", "message": "Window restored and focused."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to restore: {str(e)}"}
    return {"status": "error", "message": "No active window references found."}


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
    
    # Instantiate the bridge pattern
    api_bridge = ApiBridge()
    
    # 2. Spawn a native desktop GUI frame directing to the running server
    # Configured to look like a clean, responsive desktop interface card
    window = webview.create_window(
        title="⏱️ 自訂 PyGame 計時器",
        url="http://127.0.0.1:8000",
        js_api=api_bridge,  # Bind native Python functions to Javascript window.pywebview.api
        width=1000,
        height=750,
        resizable=True
    )
    
    # 3. Intercept window closing events to minimize to system tray instead of exiting
    window.events.closing += on_window_closing
    
    # 4. Setup the system tray menu and icon configuration
    setup_system_tray()
    
    # 5. Enter the main graphical window loop
    webview.start()