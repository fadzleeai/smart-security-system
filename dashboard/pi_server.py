"""
pi_server.py — Lightweight API server that runs ON THE RASPBERRY PI

PURPOSE
    This is the ONLY thing that runs on the Pi for dashboard purposes.
    It does NOT run Streamlit (too heavy for the Pi). It just exposes
    your existing security_logs.csv, images/ folder, and live state
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
       /state below is derived live from this CSV — no extra file needed.
    2. Save stranger images into strangers/stranger_*.jpg
    3. (For the Stop Alarm button to actually work) your detection loop
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
    GET  /state           -> live state derived from security_logs.csv
    POST /alarm/stop      -> writes alarm_dismiss.json (dashboard "Stop alarm" button)
    GET  /alarm/status    -> reads back whether alarm is currently dismissed
"""

import os
import csv
import json
import time
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

# ── CONFIG — adjust these paths to match where your backend actually writes ──
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR     = os.path.abspath(os.path.join(BASE_DIR, ".."))
CSV_PATH        = os.path.join(PROJECT_DIR, "security_logs.csv")
IMAGES_DIR      = os.path.join(PROJECT_DIR, "strangers")
ALARM_FLAG_PATH = os.path.join(BASE_DIR, "alarm_dismiss.json")

# How recent a detection event must be (in seconds) to count as "motion
# detected right now" / camera "Active" on the dashboard. Anything older
# just means nothing has happened recently, not that hardware is broken.
RECENT_EVENT_WINDOW_SECONDS = 60

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

    ISSUE 4 — Latent Logic Vulnerability (read side):
    main.py's write_log_row() now holds an exclusive fcntl lock only for
    the brief moment it appends a row. This read does NOT take a matching
    lock — deliberately: a single appended row is well under the OS's
    atomic single-write size, so a reader either sees the file before or
    after that write completes, never mid-row. Adding a lock here would
    make every dashboard refresh briefly block on the detection loop
    (or vice versa) for a protection that's already provided by how
    short, single writes work at the OS level. If rows ever grow large
    enough to need multiple write() calls, revisit this.
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
    Returns the latest known system state (door, motion, last visitor, RAM).

    REAL-TIME FIX: this used to read from a state.json file that nothing
    in the backend ever actually wrote (write_state_example() in an
    earlier version of this file was a reference snippet only — never
    called). That meant /state always returned hardcoded defaults no
    matter what the hardware was doing.

    Now it derives everything live from security_logs.csv — the same
    file your detection loop / door watcher already appends to on every
    event — so door status, last visitor, threat level, etc. reflect
    what's actually happened, with no extra file for the backend to keep
    in sync.

    pir_ok / camera_ok / door_sensor_ok / speaker_ok stay hardcoded True
    for now since there's no CSV column carrying sensor health — wire
    those up later if/when your backend logs sensor faults.
    """
    state = {
        "motion_detected":  False,
        "camera_status":    "Standby",
        "last_visitor":     "—",
        "auth_result":      "—",
        "threat_level":     "",
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

    if not os.path.exists(CSV_PATH):
        return state

    try:
        with open(CSV_PATH, "r") as f:
            rows = list(csv.DictReader(f))

        if not rows:
            return state

        # ── Door state — last door row ────────────────────────────────────
        door_rows = [r for r in rows if r.get("event_type") == "door"]
        if door_rows:
            last_door = door_rows[-1]
            door_status = last_door.get("door_status") or "Closed"
            state["door_status"] = door_status
            state["door_alert"]  = door_status == "Open"

        # ── Visitor state — last visitor row ──────────────────────────────
        visitor_rows = [r for r in rows if r.get("event_type") == "visitor"]
        if visitor_rows:
            last_v = visitor_rows[-1]

            state["last_visitor"] = last_v.get("visitor_name") or "Unknown"
            state["auth_result"]  = last_v.get("auth_result") or "—"
            state["access_count"] = len(visitor_rows)

            # Stranger image — bare filename only
            img_file = last_v.get("img_file", "")
            state["last_visitor_img"] = (
                os.path.basename(img_file) if img_file else None
            )

            # Last event time — HH:MM from timestamp
            ts = last_v.get("timestamp", "")
            state["last_event_time"] = ts[11:16] if len(ts) >= 16 else (ts or "—")

            # Threat level — keep Pi's raw value (Pending/Low/Medium/High);
            # data_source.py on the dashboard side maps it to None/Warning/Suspicious.
            state["threat_level"] = last_v.get("threat_level", "")

            # Suspicious count — Medium or High threat rows, all time in the CSV
            state["suspicious_count"] = sum(
                1 for r in visitor_rows
                if r.get("threat_level") in ("Medium", "High")
            )

            # Motion / camera status — only "Active" if the most recent
            # detection event (visitor OR door) was genuinely recent.
            try:
                last_ts = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                delta = (datetime.now() - last_ts).total_seconds()
                state["motion_detected"] = delta < RECENT_EVENT_WINDOW_SECONDS
                state["camera_status"] = (
                    "Active" if delta < RECENT_EVENT_WINDOW_SECONDS else "Standby"
                )
            except Exception:
                pass

        # If the most recent event of ANY kind is a door event newer than
        # the last visitor event, that should also count toward "recent
        # activity" for motion/camera status (e.g. door opened with no
        # face recognized yet).
        if door_rows:
            try:
                last_door_ts = datetime.strptime(
                    door_rows[-1].get("timestamp", "")[:19], "%Y-%m-%d %H:%M:%S"
                )
                delta = (datetime.now() - last_door_ts).total_seconds()
                if delta < RECENT_EVENT_WINDOW_SECONDS:
                    state["motion_detected"] = True
                    state["camera_status"] = "Active"
            except Exception:
                pass

    except Exception:
        # Keep safe defaults if the CSV is malformed mid-write etc.
        pass

    return state


@app.post("/alarm/stop")
def stop_alarm():
    """
    Called by the Streamlit dashboard Stop Alarm button.

    IMPORTANT — this does NOT silence the buzzer directly. This server
    has no GPIO access. It only writes a small flag file recording that
    a dismiss was requested. Your detection backend must separately CHECK
    this flag (see check_alarm_dismiss_example() below) and actually turn
    off the speaker/buzzer.

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
            os.remove(ALARM_FLAG_PATH)   # consume the flag so it only fires once

    Call check_and_handle_dismiss() once per loop iteration in your main
    detection loop, alongside your existing PIR/camera/door checks.
    """
    pass
