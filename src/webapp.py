import cv2
import os
import csv
import glob
import json
import time
import base64
import logging
import urllib.request
import numpy as np
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, Response, request,
    redirect, url_for, session, jsonify, flash, send_from_directory
)

# =========================================
# CONFIG
# =========================================

CONFIG_PATH     = os.environ.get("CONFIG_PATH",     "config.json")
KNOWN_FACES_DIR = os.environ.get("KNOWN_FACES_DIR", "known_faces")
LOG_FILE        = os.environ.get("LOG_FILE",        "logs/security.log")

# ── Absolute paths so routes work regardless of working directory ─────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR   = os.path.abspath(os.path.join(BASE_DIR, ".."))

STRANGERS_DIR = os.environ.get(
    "STRANGERS_DIR",
    os.path.join(PROJECT_DIR, "strangers")
)
CSV_LOG_PATH  = os.environ.get(
    "CSV_LOG_PATH",
    os.path.join(PROJECT_DIR, "/home/admin/smart-security-system/security_logs.csv")
)

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

config = load_config()

app = Flask(__name__, template_folder='../templates')
app.secret_key = os.urandom(24)

logger = logging.getLogger(__name__)

# =========================================
# STREAM PROXY
# =========================================

STREAM_PORT = config.get("stream_port", 8080)
STREAM_URL  = f"http://localhost:{STREAM_PORT}/stream"

def generate_frames():
    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(placeholder, "Security service offline", (130, 230),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(placeholder, "Start the security container first", (80, 270),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 1)
    _, placeholder_buf = cv2.imencode('.jpg', placeholder)
    placeholder_bytes  = placeholder_buf.tobytes()

    while True:
        try:
            with urllib.request.urlopen(STREAM_URL, timeout=3) as stream:
                logger.info("Connected to security stream.")
                bytes_buf = b""
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    bytes_buf += chunk
                    start = bytes_buf.find(b'\xff\xd8')
                    end   = bytes_buf.find(b'\xff\xd9')
                    if start != -1 and end != -1:
                        jpg       = bytes_buf[start:end + 2]
                        bytes_buf = bytes_buf[end + 2:]
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
        except Exception:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + placeholder_bytes + b'\r\n')
            time.sleep(2)

def camera_is_available() -> bool:
    try:
        urllib.request.urlopen(
            f"http://localhost:{STREAM_PORT}/stream", timeout=1
        ).close()
        return True
    except Exception:
        return False

# =========================================
# HELPERS
# =========================================

def decode_base64_image(data_url: str):
    header, encoded = data_url.split(',', 1)
    img_bytes  = base64.b64decode(encoded)
    img_array  = np.frombuffer(img_bytes, np.uint8)
    return cv2.imdecode(img_array, cv2.IMREAD_COLOR)

def validate_and_save_face(img, name: str) -> tuple[bool, str]:
    if img is None:
        return False, "Could not read image."
    os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
    path = os.path.join(KNOWN_FACES_DIR, f"{name}.jpg")
    cv2.imwrite(path, img)
    return True, f"Face registered for {name}!"

# =========================================
# AUTH
# =========================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# =========================================
# ROUTES — AUTH
# =========================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        expected = config.get("web_password", "admin123")
        if password == expected:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("Wrong password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# =========================================
# ROUTES — DASHBOARD
# =========================================

@app.route("/")
@login_required
def dashboard():
    strangers = []
    if os.path.exists(STRANGERS_DIR):
        files = sorted(
            [f for f in os.listdir(STRANGERS_DIR) if f.endswith(".jpg")],
            reverse=True
        )[:6]
        for f in files:
            parts = f.replace(".jpg", "").split("_")
            try:
                date     = parts[1]
                time_str = parts[2]
                risk     = parts[3] if len(parts) > 3 else "Unknown"
                dt       = datetime.strptime(f"{date}_{time_str}", "%Y%m%d_%H%M%S")
                strangers.append({
                    "filename": f,
                    "risk":     risk,
                    "time":     dt.strftime("%d %b %Y, %H:%M:%S"),
                })
            except Exception:
                strangers.append({
                    "filename": f, "risk": "Unknown", "time": "Unknown"
                })

    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as lf:
            lines = lf.readlines()
            logs  = [l.strip() for l in lines[-20:] if l.strip()][::-1]

    return render_template("dashboard.html",
                           strangers=strangers,
                           logs=logs,
                           camera_available=camera_is_available())

# =========================================
# ROUTES — CAMERA FEED
# =========================================

@app.route("/video_feed")
@login_required
def video_feed():
    return Response(generate_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/camera_status")
@login_required
def camera_status():
    return jsonify({"available": camera_is_available()})

# =========================================
# ROUTES — REGISTER FACE
# =========================================

@app.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if request.method == "POST":
        name   = request.form.get("name", "").strip()
        source = request.form.get("source", "local")

        if not name:
            flash("Name is required.")
            return redirect(url_for("register"))

        if source == "local":
            data_url = request.form.get("captured_image", "")
            if not data_url or not data_url.startswith("data:image"):
                flash("No photo captured. Please capture a photo first.")
                return redirect(url_for("register"))
            img      = decode_base64_image(data_url)
            ok, msg  = validate_and_save_face(img, name)
            flash(msg)
            return redirect(url_for("register"))

        elif source == "rpi":
            if not camera_is_available():
                flash("Security stream is offline. Start the security container first.")
                return redirect(url_for("register"))
            try:
                with urllib.request.urlopen(STREAM_URL, timeout=5) as stream:
                    bytes_buf = b""
                    while True:
                        chunk = stream.read(4096)
                        if not chunk:
                            break
                        bytes_buf += chunk
                        start = bytes_buf.find(b'\xff\xd8')
                        end   = bytes_buf.find(b'\xff\xd9')
                        if start != -1 and end != -1:
                            jpg       = bytes_buf[start:end + 2]
                            img_array = np.frombuffer(jpg, np.uint8)
                            img       = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                            break
                ok, msg = validate_and_save_face(img, name)
                flash(msg)
            except Exception as e:
                logger.error(f"Failed to grab frame from stream: {e}")
                flash("Failed to capture from RPi camera. Try again.")
            return redirect(url_for("register"))

    faces = []
    if os.path.exists(KNOWN_FACES_DIR):
        faces = [
            os.path.splitext(f)[0]
            for f in os.listdir(KNOWN_FACES_DIR)
            if f.lower().endswith((".jpg", ".png"))
        ]

    return render_template("register.html",
                           faces=faces,
                           camera_available=camera_is_available())

# =========================================
# ROUTES — DELETE FACE
# =========================================

@app.route("/delete_face/<name>", methods=["POST"])
@login_required
def delete_face(name):
    for ext in [".jpg", ".png"]:
        path = os.path.join(KNOWN_FACES_DIR, f"{name}{ext}")
        if os.path.exists(path):
            os.remove(path)
            flash(f"Deleted {name}.")
            return redirect(url_for("register"))
    flash("Face not found.")
    return redirect(url_for("register"))

# =========================================
# ROUTES — STRANGER IMAGE
# =========================================

@app.route("/stranger/<filename>")
def stranger_image(filename):
    """
    Serves stranger images.
    NOTE: login_required removed so Streamlit dashboard can fetch images
    directly via the Cloudflare tunnel without a session cookie.
    """
    return send_from_directory(os.path.abspath(STRANGERS_DIR), filename)

# =========================================
# ROUTES — STREAMLIT DASHBOARD API
# Three endpoints added for the Streamlit dashboard to consume over the
# Cloudflare tunnel. No login required — data is non-sensitive telemetry.
# =========================================

@app.route("/logs")
def serve_logs():
    """
    Serves security_logs.csv as text/csv.
    Streamlit reads this via pandas.read_csv().
    """
    if not os.path.exists(CSV_LOG_PATH):
        return jsonify({"detail": "security_logs.csv not found yet"}), 404
    with open(CSV_LOG_PATH, "r") as f:
        content = f.read()
    return Response(content, mimetype="text/csv")


@app.route("/state")
def serve_state():
    """
    Returns latest system state as JSON for Page 1 real-time monitoring.
    Derives state from the last rows of security_logs.csv.
    """
    # Safe defaults
    state = {
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
            "os_streamlit_mb":     600,
            "face_recognition_mb": 350,
            "opencv_camera_mb":    150,
            "mqtt_sensors_mb":      40,
            "total_pi_ram_mb":    4096,
        }
    }

    if not os.path.exists(CSV_LOG_PATH):
        return jsonify(state)

    try:
        with open(CSV_LOG_PATH, "r") as f:
            rows = list(csv.DictReader(f))

        if not rows:
            return jsonify(state)

        # ── Door state — last door row ────────────────────────────────────
        door_rows = [r for r in rows if r.get("event_type") == "door"]
        if door_rows:
            last_door            = door_rows[-1]
            door_status          = last_door.get("door_status", "Closed")
            state["door_status"] = door_status
            state["door_alert"]  = door_status == "Open"

        # ── Visitor state — last visitor row ─────────────────────────────
        visitor_rows = [r for r in rows if r.get("event_type") == "visitor"]
        if visitor_rows:
            last_v = visitor_rows[-1]

            state["last_visitor"]  = last_v.get("visitor_name") or "Unknown"
            state["auth_result"]   = last_v.get("auth_result")  or "—"
            state["access_count"]  = len(visitor_rows)

            # Stranger image — bare filename only
            img_file = last_v.get("img_file", "")
            state["last_visitor_img"] = (
                os.path.basename(img_file) if img_file else None
            )

            # Last event time — HH:MM from timestamp
            ts = last_v.get("timestamp", "")
            try:
                state["last_event_time"] = ts[11:16] if len(ts) >= 16 else ts
            except Exception:
                state["last_event_time"] = "—"

            # Threat level — keep Pi's raw value; data_source.py maps it
            state["threat_level"] = last_v.get("threat_level", "")

            # Suspicious count — Medium or High threat rows
            state["suspicious_count"] = sum(
                1 for r in visitor_rows
                if r.get("threat_level") in ("Medium", "High")
            )

            # Motion detected if last visitor was recent (within 60 s)
            try:
                last_ts = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                delta   = (datetime.now() - last_ts).total_seconds()
                state["motion_detected"]  = delta < 60
                state["camera_status"]    = "Active" if delta < 60 else "Standby"
            except Exception:
                pass

    except Exception as e:
        logger.error(f"/state error: {e}")

    return jsonify(state)


@app.route("/images-list")
def serve_images_list():
    """
    Returns list of stranger image filenames for the Streamlit gallery.
    """
    if not os.path.exists(STRANGERS_DIR):
        return jsonify({"images": []})

    files = sorted([
        os.path.basename(f)
        for f in glob.glob(os.path.join(STRANGERS_DIR, "stranger_*.jpg"))
    ], reverse=True)   # newest first

    return jsonify({"images": files})


@app.route("/alarm/stop", methods=["POST"])
def alarm_stop():
    """
    Called by the Streamlit dashboard Stop Alarm button.
    Extend this to trigger GPIO/speaker when MQTT is ready.
    """
    logger.info("Alarm stop requested from dashboard.")
    # ── MQTT SWAP ────────────────────────────────────────────────────────────
    # When MQTT is ready, add:
    #   import paho.mqtt.publish as publish
    #   publish.single("security/alarm/stop", "1", hostname="localhost")
    # ────────────────────────────────────────────────────────────────────────
    return jsonify({"success": True, "message": "Alarm stop command received."})


# =========================================
# RUN
# =========================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.get("web_port", 5000), debug=False)
