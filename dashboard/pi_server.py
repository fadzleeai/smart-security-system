"""
pi_server.py — Lightweight API server that runs ON THE RASPBERRY PI

PURPOSE
    This is the ONLY thing that runs on the Pi for dashboard purposes.
    It does NOT run Streamlit (too heavy for the Pi). It just exposes
    your existing security_logs.csv, images/ folder, and a small state.json
    over HTTP, so the cloud-hosted Streamlit app can fetch them.

    Your face recognition / sensor backend code does NOT change at all.
    This file only READS what your backend already writes.

WHY THIS IS LIGHT ON RAM
    FastAPI + uvicorn idle ≈ 30-50 MB RAM (vs ~600 MB for Streamlit).
    It does no work until a request actually arrives.

RUN THIS ON THE PI
    pip install fastapi uvicorn
    python3 pi_server.py
    (or run it in the background — see "Run as a background service" below)

WHAT YOUR BACKEND MUST KEEP DOING (unchanged)
    1. Append rows to security_logs.csv after every detection event.
    2. Save stranger images into images/stranger_*.jpg
    3. (Optional, for Page 1 near-real-time) write the current state to
       state.json every time something changes — see write_state_example()
       at the bottom of this file for the 5 lines to add to your backend.
    4. (For the Stop Alarm button to actually work) your detection loop
       must occasionally CHECK alarm_dismiss.json — see
       check_alarm_dismiss_example() at the bottom of this file. This
       server only writes the flag; it has no GPIO access, so it cannot
       silence the buzzer itself. Your backend has to read the flag and
       act on it.

ENDPOINTS THIS SERVER PROVIDES
    GET  /health         -> {"status": "ok"}            (tunnel/uptime check)
    GET  /logs            -> raw CSV file content
    GET  /images/<file>   -> serves one image file
    GET  /images-list     -> list of available image filenames
    GET  /state           -> contents of state.json (Page 1 live-ish data)
    POST /alarm/stop      -> writes alarm_dismiss.json (dashboard "Stop alarm" button)
    GET  /alarm/status    -> reads back whether alarm is currently dismissed
"""

import os
import json
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

# ── CONFIG — adjust these paths to match where your backend actually writes ──
BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
CSV_PATH          = "/home/admin/smart-security-system/security_logs.csv"
IMAGES_DIR        = os.path.join(BASE_DIR, "images")
STATE_PATH        = os.path.join(BASE_DIR, "state.json")
ALARM_FLAG_PATH   = os.path.join(BASE_DIR, "alarm_dismiss.json")

app = FastAPI(title="Pi Security Data API")

# Allow Streamlit Cloud (or any origin) to call this API.
# Fine for a student project; for production you'd restrict allow_origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Simple check the tunnel + server are alive."""
    return {"status": "ok"}


@app.get("/logs", response_class=PlainTextResponse)
def get_logs():
    """
    Returns the raw CSV content as plain text.
    The Streamlit side will parse this into a DataFrame.
    """
    if not os.path.exists(CSV_PATH):
        raise HTTPException(status_code=404, detail="security_logs.csv not found yet")
    with open(CSV_PATH, "r") as f:
        return f.read()


@app.get("/images-list")
def list_images():
    """
    Returns just the filenames of stranger images (not the files themselves).
    Dashboard uses this to know what to request via /images/<filename>.
    """
    if not os.path.isdir(IMAGES_DIR):
        return {"images": []}
    files = sorted([
        f for f in os.listdir(IMAGES_DIR)
        if f.startswith("stranger_") and f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    return {"images": files}


@app.get("/images/{filename}")
def get_image(filename: str):
    """
    Serves a single image file by name.
    Basic safety: only allow filenames that look like our own stranger images,
    and block any path traversal attempts (../ etc).
    """
    safe_name = os.path.basename(filename)  # strips any ../ tricks
    if not safe_name.startswith("stranger_"):
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = os.path.join(IMAGES_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)


@app.get("/state")
def get_state():
    """
    Returns the latest known system state (door, motion, RAM, sensors).
    This is the "every few seconds" near-real-time piece for Page 1.

    Your backend should overwrite state.json each time something changes
    (see write_state_example() below for the snippet to drop into your
    detection loop). If state.json doesn't exist yet, we return safe mock
    defaults so the dashboard doesn't crash before your backend writes one.
    """
    if not os.path.exists(STATE_PATH):
        return {
            "motion_detected":  False,
            "camera_status":    "Standby",
            "last_visitor":     "—",
            "auth_result":      "—",
            "threat_level":     "None",
            "suspicious_count": 0,
            "door_status":      "Closed",
            "door_alert":       False,
            "pir_ok":           True,
            "camera_ok":        True,
            "door_sensor_ok":   True,
            "speaker_ok":       True,
            "last_visitor_img": None,
            "last_event_time":  "—",
            "access_count":     0,
            "ram": {
                "os_streamlit_mb":     0,
                "face_recognition_mb": 0,
                "opencv_camera_mb":    0,
                "mqtt_sensors_mb":     0,
                "total_pi_ram_mb":     4096,
            },
        }
    with open(STATE_PATH, "r") as f:
        return json.load(f)


@app.post("/alarm/stop")
def stop_alarm():
    """
    Called when someone clicks "Stop alarm" on the dashboard.

    IMPORTANT — this does NOT silence the buzzer directly. This server
    has no GPIO access. It only writes a small flag file recording that
    a dismiss was requested. Your detection backend must separately CHECK
    this flag (see check_alarm_dismiss_example() below) and actually turn
    off the speaker/buzzer, then ideally update state.json so threat_level
    reflects the dismissal too.

    Returns the flag contents so the dashboard can confirm it was written.
    """
    flag = {
        "dismissed": True,
        "dismissed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(ALARM_FLAG_PATH, "w") as f:
        json.dump(flag, f)
    return flag


@app.get("/alarm/status")
def alarm_status():
    """
    Lets the dashboard check whether a dismiss is currently in effect —
    useful if you want the "Stop alarm" button to show as already-pressed
    after a page refresh, instead of resetting every reload.
    """
    if not os.path.exists(ALARM_FLAG_PATH):
        return {"dismissed": False, "dismissed_at": None}
    with open(ALARM_FLAG_PATH, "r") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Run directly with: python3 pi_server.py
# (uvicorn is the actual web server underneath FastAPI)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # host="0.0.0.0" so Cloudflare Tunnel (running locally too) can reach it
    uvicorn.run(app, host="0.0.0.0", port=8000)


def write_state_example():
    """
    NOT CALLED — this is a copy-paste reference for your backend developer
    (Student 3 / Student 4). Drop this snippet into your detection loop
    anywhere the system state changes (motion detected, door opens, auth
    result determined, etc). Keep it cheap — just dumping a small dict to
    a JSON file, no extra dependencies.

    import json

    def update_state(motion, camera_status, last_visitor, auth_result,
                      threat_level, suspicious_count, door_status,
                      last_visitor_img, last_event_time, access_count,
                      ram_dict):
        state = {
            "motion_detected":  motion,
            "camera_status":    camera_status,
            "last_visitor":     last_visitor,
            "auth_result":      auth_result,
            "threat_level":     threat_level,
            "suspicious_count": suspicious_count,
            "door_status":      door_status,
            "door_alert":       door_status == "Open",
            "pir_ok": True, "camera_ok": True,
            "door_sensor_ok": True, "speaker_ok": True,
            "last_visitor_img": last_visitor_img,   # e.g. "stranger_004.jpg"
            "last_event_time":  last_event_time,
            "access_count":     access_count,
            "ram": ram_dict,
        }
        with open("state.json", "w") as f:
            json.dump(state, f)

    Call update_state(...) right after each detection event resolves.
    """
    pass


def check_alarm_dismiss_example():
    """
    NOT CALLED — copy-paste reference for your backend developer.

    Your detection loop should periodically (e.g. once per loop iteration,
    or once a second) check whether the dashboard requested an alarm stop,
    and if so, silence the buzzer and clear the flag so it doesn't fire
    again on the next real alert.

    import json, os

    ALARM_FLAG_PATH = "alarm_dismiss.json"

    def check_and_handle_dismiss():
        if not os.path.exists(ALARM_FLAG_PATH):
            return
        with open(ALARM_FLAG_PATH, "r") as f:
            flag = json.load(f)
        if flag.get("dismissed"):
            # silence_buzzer() — your actual GPIO/speaker-off call
            # Optionally also reset threat_level in your next state.json write
            os.remove(ALARM_FLAG_PATH)   # consume the flag so it only fires once

    Call check_and_handle_dismiss() once per loop iteration in your main
    detection loop, alongside your existing PIR/camera/door checks.
    """
    pass
