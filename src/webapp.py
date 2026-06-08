import cv2
import os
import json
import time
import base64
import threading
import logging
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, Response, request,
    redirect, url_for, session, jsonify, flash
)
import face_recognition
import numpy as np

# =========================================
# CONFIG
# =========================================

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
KNOWN_FACES_DIR = os.environ.get("KNOWN_FACES_DIR", "known_faces")
STRANGERS_DIR = os.environ.get("STRANGERS_DIR", "strangers")
LOG_FILE = os.environ.get("LOG_FILE", "logs/security.log")

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

config = load_config()

app = Flask(__name__, template_folder='../templates')
app.secret_key = os.urandom(24)

logger = logging.getLogger(__name__)

# =========================================
# CAMERA STREAM (RPi camera)
# =========================================

camera = None
camera_lock = threading.Lock()
camera_available = False

def get_camera():
    global camera, camera_available
    with camera_lock:
        if camera is None or not camera.isOpened():
            camera = cv2.VideoCapture(config.get("camera_index", 0))
            camera_available = camera.isOpened()
        return camera

def generate_frames():
    global camera_available
    cam = get_camera()
    if not cam.isOpened():
        camera_available = False
        return

    while True:
        with camera_lock:
            success, frame = cam.read()
        if not success:
            camera_available = False
            break

        camera_available = True
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.033)

# =========================================
# HELPERS
# =========================================

def decode_base64_image(data_url: str):
    """Convert base64 data URL from browser to OpenCV image."""
    header, encoded = data_url.split(',', 1)
    img_bytes = base64.b64decode(encoded)
    img_array = np.frombuffer(img_bytes, np.uint8)
    return cv2.imdecode(img_array, cv2.IMREAD_COLOR)

def validate_and_save_face(img, name: str) -> tuple[bool, str]:
    """Check face exists in image and save to known_faces. Returns (success, message)."""
    if img is None:
        return False, "Could not read image."

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    locs = face_recognition.face_locations(rgb)
    if not locs:
        return False, "No face detected. Try again."

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
                date = parts[1]
                time_str = parts[2]
                risk = parts[3] if len(parts) > 3 else "Unknown"
                dt = datetime.strptime(f"{date}_{time_str}", "%Y%m%d_%H%M%S")
                strangers.append({
                    "filename": f,
                    "risk": risk,
                    "time": dt.strftime("%d %b %Y, %H:%M:%S")
                })
            except Exception:
                strangers.append({"filename": f, "risk": "Unknown", "time": "Unknown"})

    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as lf:
            lines = lf.readlines()
            logs = [l.strip() for l in lines[-20:] if l.strip()][::-1]

    return render_template("dashboard.html",
                           strangers=strangers,
                           logs=logs,
                           camera_available=camera_available)

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
    return jsonify({"available": camera_available})

# =========================================
# ROUTES — REGISTER FACE
# =========================================

@app.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        source = request.form.get("source", "local")

        if not name:
            flash("Name is required.")
            return redirect(url_for("register"))

        if source == "local":
            # Browser webcam capture — comes as base64 data URL
            data_url = request.form.get("captured_image", "")
            if not data_url or not data_url.startswith("data:image"):
                flash("No photo captured. Please capture a photo first.")
                return redirect(url_for("register"))

            img = decode_base64_image(data_url)
            ok, msg = validate_and_save_face(img, name)
            flash(msg)
            return redirect(url_for("register"))

        elif source == "rpi":
            # Capture from RPi camera server-side
            cam = get_camera()
            if not cam.isOpened():
                flash("RPi camera is offline.")
                return redirect(url_for("register"))

            with camera_lock:
                ret, frame = cam.read()

            if not ret:
                flash("Failed to capture from RPi camera.")
                return redirect(url_for("register"))

            ok, msg = validate_and_save_face(frame, name)
            flash(msg)
            return redirect(url_for("register"))

    faces = []
    if os.path.exists(KNOWN_FACES_DIR):
        faces = [os.path.splitext(f)[0] for f in os.listdir(KNOWN_FACES_DIR)
                 if f.lower().endswith((".jpg", ".png"))]

    return render_template("register.html", faces=faces, camera_available=camera_available)

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
@login_required
def stranger_image(filename):
    from flask import send_from_directory
    return send_from_directory(os.path.abspath(STRANGERS_DIR), filename)

# =========================================
# RUN
# =========================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)