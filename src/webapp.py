import cv2
import os
import json
import time
import base64
import logging
import socket
import urllib.request
import numpy as np
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, Response, request,
    redirect, url_for, session, jsonify, flash
)

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
# STREAM PROXY — proxies from security container
# =========================================

STREAM_PORT = config.get("stream_port", 8080)
STREAM_URL = f"http://localhost:{STREAM_PORT}/stream"

def generate_frames():
    """Proxy the MJPEG stream from main.py's stream server.

    Uses a raw socket instead of urllib.request: urllib's `timeout`
    applies to every individual socket read, not just connection setup.
    Since /stream is a live MJPEG feed, there can be gaps between frames
    (e.g. while motion isn't active main.py still pushes ~30fps, but any
    hiccup can exceed a short urllib timeout and kill an otherwise-healthy
    connection). Here we use a short connect timeout (fail fast if main.py
    is down) and a separate, more generous read timeout.
    """
    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(placeholder, "Camera service offline", (130, 230),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.putText(placeholder, "Start main.py first", (140, 270),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 1)
    _, placeholder_buf = cv2.imencode('.jpg', placeholder)
    placeholder_bytes = placeholder_buf.tobytes()

    CONNECT_TIMEOUT = 2
    READ_TIMEOUT = 10  # generous: tolerates brief stalls between frames

    while True:
        sock = None
        try:
            sock = socket.create_connection(("localhost", STREAM_PORT), timeout=CONNECT_TIMEOUT)
            sock.settimeout(READ_TIMEOUT)
            request = f"GET /stream HTTP/1.1\r\nHost: localhost:{STREAM_PORT}\r\nConnection: close\r\n\r\n"
            sock.sendall(request.encode())

            logger.info("Connected to camera stream.")
            bytes_buf = b""
            headers_done = False

            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                bytes_buf += chunk

                if not headers_done:
                    header_end = bytes_buf.find(b"\r\n\r\n")
                    if header_end == -1:
                        continue
                    bytes_buf = bytes_buf[header_end + 4:]
                    headers_done = True

                start = bytes_buf.find(b'\xff\xd8')  # JPEG start
                end = bytes_buf.find(b'\xff\xd9')    # JPEG end
                if start != -1 and end != -1 and end > start:
                    jpg = bytes_buf[start:end + 2]
                    bytes_buf = bytes_buf[end + 2:]
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
        except Exception as e:
            logger.error(f"Stream proxy error: {e!r}")
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + placeholder_bytes + b'\r\n')
            time.sleep(2)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

def camera_is_available() -> bool:
    """
    Check whether main.py's stream server is up by opening a raw TCP
    connection to its port. We deliberately do NOT use urllib/requests
    here: /stream is an infinite MJPEG generator that never finishes
    sending a body, so a normal HTTP GET (even with a short timeout)
    can time out waiting on the body even though the server is healthy
    and already sent valid headers. A plain socket connect tells us
    "is something listening on this port" without touching the stream.
    """
    try:
        with socket.create_connection(("localhost", STREAM_PORT), timeout=1):
            return True
    except OSError:
        return False

# =========================================
# HELPERS
# =========================================

def decode_base64_image(data_url: str):
    header, encoded = data_url.split(',', 1)
    img_bytes = base64.b64decode(encoded)
    img_array = np.frombuffer(img_bytes, np.uint8)
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
        name = request.form.get("name", "").strip()
        source = request.form.get("source", "local")

        if not name:
            flash("Name is required.")
            return redirect(url_for("register"))

        if source == "local":
            data_url = request.form.get("captured_image", "")
            if not data_url or not data_url.startswith("data:image"):
                flash("No photo captured. Please capture a photo first.")
                return redirect(url_for("register"))
            img = decode_base64_image(data_url)
            ok, msg = validate_and_save_face(img, name)
            flash(msg)
            return redirect(url_for("register"))

        elif source == "rpi":
            if not camera_is_available():
                flash("Camera stream is offline. Start main.py first.")
                return redirect(url_for("register"))
            try:
                # Grab a single frame from the existing MJPEG stream
                with urllib.request.urlopen(STREAM_URL, timeout=5) as stream:
                    bytes_buf = b""
                    while True:
                        chunk = stream.read(4096)
                        if not chunk:
                            break
                        bytes_buf += chunk
                        start = bytes_buf.find(b'\xff\xd8')
                        end = bytes_buf.find(b'\xff\xd9')
                        if start != -1 and end != -1:
                            jpg = bytes_buf[start:end + 2]
                            img_array = np.frombuffer(jpg, np.uint8)
                            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                            break
                ok, msg = validate_and_save_face(img, name)
                flash(msg)
            except Exception as e:
                logger.error(f"Failed to grab frame from stream: {e}")
                flash("Failed to capture from RPi camera. Try again.")
            return redirect(url_for("register"))

    faces = []
    if os.path.exists(KNOWN_FACES_DIR):
        faces = [os.path.splitext(f)[0] for f in os.listdir(KNOWN_FACES_DIR)
                 if f.lower().endswith((".jpg", ".png"))]

    return render_template("register.html", faces=faces, camera_available=camera_is_available())

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
    # NOTE: ssl_context="adhoc" intentionally removed. Werkzeug's dev-server
    # SSL wrapper does not handle long-lived streaming responses (MJPEG)
    # reliably and crashes with ssl.SSLError during chunked writes once the
    # connection is held open for video_feed. This is a local-network tool,
    # so plain HTTP is fine. If HTTPS is required later, put this behind a
    # real reverse proxy (nginx/caddy) instead of Werkzeug's adhoc SSL.
    app.run(host="0.0.0.0", port=config.get("web_port", 5000), debug=False)