from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time
import sqlite3

app = FastAPI()

# Enable CORS for the frontend development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"], # Common dev ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("timers.db")
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

init_db()


# --- PYDANTIC DATA MODELS ---
class TimerRequest(BaseModel):
    duration_seconds: int

class SaveTimerRequest(BaseModel):
    label: str
    duration_seconds: int


# --- API ENDPOINTS ---
@app.get("/")
def read_root():
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