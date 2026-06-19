from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # Vue's default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# This defines what data the frontend must send us
class TimerRequest(BaseModel):
    duration_seconds: int

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Timer API is running"}

@app.post("/api/timer/start")
def start_timer(request: TimerRequest):
    if request.duration_seconds <= 0:
        raise HTTPException(
            status_code=400, 
            detail="Duration must be greater than 0 seconds")
        
    current_time = time.time()
    end_time = current_time + request.duration_seconds
    
    return {
        "status": "started",
        "duration": request.duration_seconds,
        "end_time": end_time
    }