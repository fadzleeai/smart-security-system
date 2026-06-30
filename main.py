import cv2
import time
import json
import logging
import os
import sys
import threading
import argparse
import fcntl
from flask import Flask, Response

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except (ImportError, RuntimeError):
    PICAMERA2_AVAILABLE = False

# =========================================
# SMART CAMERA ADAPTER
# =========================================
class Camera:
    def __init__(self, camera_index: int, mode: str = "auto", width: int = 640, height: int = 480):
        self.backend = None
        self._picam = None
        self._cv_cap = None
        self.init_error = None

        # 1. Try picamera2 if requested or in auto mode
        if mode in ["auto", "picamera2"] and PICAMERA2_AVAILABLE:
            try:
                self._picam = Picamera2()
                config = self._picam.create_video_configuration(
                    main={"size": (width, height), "format": "RGB888"}
                )
                self._picam.configure(config)
                self._picam.start()
                time.sleep(1)  # let auto-exposure/white-balance settle
                self.backend = "picamera2"
            except Exception as exc:
                if mode == "picamera2":
                    self.init_error = f"picamera2 requested but failed: {exc}"
                self._picam = None

        # 2. Try USB Webcam (V4L2) if requested or if auto fell through
        if self.backend is None and mode in ["auto", "webcam"]:
            self._cv_cap = cv2.VideoCapture(camera_index, cv2.CAP_V4L2)
            if self._cv_cap.isOpened():
                self._cv_cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self._cv_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                self.backend = "webcam (V4L2)"
            else:
                if mode == "webcam":
                    self.init_error = f"Failed to open USB camera at index {camera_index} using V4L2."

        # 3. Final safety fallback to standard OpenCV
        if self.backend is None and mode == "auto":
            self._cv_cap = cv2.VideoCapture(camera_index)
            if self._cv_cap.isOpened():
                self.backend = "cv2 (default)"
            else:
                self.init_error = "All camera initializations failed."

    def isOpened(self) -> bool:
        return self.backend is not None

    def read(self):
        """Returns (ret, frame) as BGR."""
        if self.backend == "picamera2":
            try:
                frame_rgb = self._picam.capture_array()
                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                return True, frame_bgr
            except Exception:
                return False, None
        elif self.backend and "webcam" in self.backend or "cv2" in self.backend:
            return self._cv_cap.read()
        return False, None

    def release(self):
        if self.backend == "picamera2" and self._picam is not None:
            try:
                self._picam.stop()
            except Exception:
                pass
        elif self._cv_cap is not None:
            self._cv_cap.release()

# =========================================
# LOGGING SETUP
# =========================================
def setup_logging(log_to_file: bool, log_file: str):
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_to_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers
    )

# =========================================
# LOAD CONFIG
# =========================================
CONFIG_PATH     = os.environ.get("CONFIG_PATH",     "config.json")
KNOWN_FACES_DIR = os.environ.get("KNOWN_FACES_DIR", "known_faces")
STRANGERS_DIR   = os.environ.get("STRANGERS_DIR",   "strangers")
MODELS_DIR      = os.environ.get("MODELS_DIR",      "models")
CSV_LOG_PATH    = os.environ.get("CSV_LOG_PATH",    "/home/admin/smart-security-system/security_logs.csv")

# Same file pi_server.py writes via POST /alarm/stop. pi_server.py's
# ALARM_FLAG_PATH is relative to ITS OWN folder (dashboard/), confirmed
# against its BASE_DIR/PROJECT_DIR setup — main.py runs from the project
# root one level up, so this needs the dashboard/ prefix to find the
# exact same physical file, not a relative "alarm_dismiss.json" which
# main.py running from a different working directory.
ALARM_FLAG_PATH = os.environ.get(
    "ALARM_FLAG_PATH",
    "/home/admin/smart-security-system/dashboard/alarm_dismiss.json",
)

# New, per explicit feedback: the stranger popup previously kept
# re-appearing until the owner manually tagged it, regardless of
# whether the person had actually left — confirmed they want it tied
# to LIVE camera presence instead, stopping the moment the person
# leaves frame even if never tagged. main.py is the only process that
# actually knows "is an unrecognized face in frame RIGHT NOW" (the
# current_results variable in the detection loop) — pi_server.py runs
# as a separate OS process and can't read that variable directly, so
# this file is the bridge: touched every frame a stranger is detected,
# left stale (not touched) the moment they leave. pi_server.py checks
# this file's mtime — recent means "still here", stale means "gone" —
# same proven pattern as RECENT_EVENT_WINDOW_SECONDS already used for
# motion_detected/camera_status in pi_server.py's /state endpoint.
STRANGER_HEARTBEAT_PATH = os.environ.get(
    "STRANGER_HEARTBEAT_PATH",
    "/home/admin/smart-security-system/dashboard/stranger_heartbeat.json",
)

# URGENT FIX, per explicit conversation: if main.py crashes or hangs for
# ANY reason (unhandled exception, camera disconnect, power blip), the
# ENTIRE detection system — door watcher, speaker, stranger detection —
# silently stops, with NOTHING telling the owner it happened. This is
# the single worst-case failure mode discussed: every other limitation
# (sensor faults, tunnel drops) assumes main.py is still running at all;
# this is the one where that assumption itself breaks. Touched on EVERY
# iteration of the main camera loop below (not gated by motion/scanning
# state), so a stale timestamp genuinely means "the process itself is
# stuck or dead", not just "nothing happened recently".
SYSTEM_HEARTBEAT_PATH = os.environ.get(
    "SYSTEM_HEARTBEAT_PATH",
    "/home/admin/smart-security-system/dashboard/system_heartbeat.json",
)

# How often a NEW photo/CSV row gets created for the SAME lingering
# unrecognized person. CHANGED per explicit feedback: at the previous
# 10s interval, someone standing in frame for a couple of minutes
# produced a new "pending stranger" entry every 10 seconds — since each
# one has a distinct filename, /stranger/pending treats EACH as a
# separate, fresh thing needing review, so the dashboard popup kept
# reappearing for what was really the same single visit. This does NOT
# affect how fast a genuinely NEW/different person triggers their own
# first alert — that's still immediate, this only throttles REPEAT
# saves for one continuous, ongoing detection of the same person.
STRANGER_SAVE_INTERVAL_SECONDS = 60

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

# =========================================
# CSV EVENT LOG  (read by the cloud dashboard via pi_server.py)
# =========================================
CSV_HEADER = "timestamp,event_type,visitor_name,auth_result,threat_level,door_status,confidence,img_file\n"

def write_log_row(logger, event_type, visitor_name="", auth_result="",
                   threat_level="", door_status="", confidence="", img_file=""):
    """
    Appends one row to security_logs.csv. Used for two kinds of rows:
      event_type="visitor" — a face was recognized (Authorized or Denied)
      event_type="door"    — the door itself opened/closed, independent of
                              whether any face was ever recognized
    Writing the header once if the file doesn't exist yet, then appending,
    keeps this safe to call repeatedly without ever overwriting history.

    ISSUE 4 FIX — Latent Logic Vulnerability:
    fcntl.flock() makes the "does the file exist yet -> maybe write header
    -> write row" sequence atomic across callers, even if main.py's
    background threads (door watcher, entry_lockout_handler) ever call
    this concurrently. Without the lock, two near-simultaneous calls could
    both see "no file yet" and both write a header, corrupting the CSV
    with a duplicate header row in the middle of the data.

    This does NOT protect against pi_server.py reading the file via a
    separate OS process while this write is in progress — flock() only
    coordinates locks within the same locking scheme, and a plain
    open(path, "r") on the read side doesn't request a lock at all. See
    the matching note in pi_server.py's get_logs() for why a short
    single-line append is still safe to read concurrently in practice.
    """
    try:
        with open(CSV_LOG_PATH, "a") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                file_exists = os.path.isfile(CSV_LOG_PATH) and f.tell() > 0
                if not file_exists:
                    f.write(CSV_HEADER)
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                row = f"{timestamp},{event_type},{visitor_name},{auth_result}," \
                      f"{threat_level},{door_status},{confidence},{img_file}\n"
                f.write(row)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.error(f"Failed to write CSV log row: {e}")

# =========================================
# SAVE STRANGER IMAGE
# =========================================
def save_stranger(frame, risk: str, logger):
    """Returns the saved filename (no folder prefix) on success, else None."""
    try:
        os.makedirs(STRANGERS_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"stranger_{timestamp}_{risk}.jpg"
        cv2.imwrite(os.path.join(STRANGERS_DIR, filename), frame)
        logger.info(f"Stranger image saved: {filename}")
        return filename
    except Exception as e:
        logger.error(f"Failed to save stranger image: {e}")
        return None

# =========================================
# DRAW RESULTS ON FRAME
# =========================================
def draw_results(frame, results, scale: int = 2):
    for result in results:
        top, right, bottom, left = result["location"]
        top    *= scale
        right  *= scale
        bottom *= scale
        left   *= scale

        action = result.get("action", "DENIED")
        if action == "AUTHORIZED":
            color = (0, 180, 0)
        elif action == "DENIED":
            color = (0, 0, 255)
        else:
            color = (0, 165, 255)

        name      = result["name"]
        risk      = result.get("risk", "")
        liveness  = result.get("liveness", "")
        conf      = result.get("confidence", 0.0)

        lines = [
            f"{name} | {action}",
            f"Risk: {risk} | Conf: {conf:.0%}",
            f"Liveness: {liveness}",
        ]

        panel_top    = max(0, top - 60)
        panel_right  = min(frame.shape[1] - 1, left + 380)
        cv2.rectangle(frame, (left, panel_top), (panel_right, top), color, cv2.FILLED)
        for i, line in enumerate(lines):
            cv2.putText(frame, line, (left + 5, panel_top + 18 + i * 19),
                        cv2.FONT_HERSHEY_DUPLEX, 0.48, (255, 255, 255), 1)

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

    return frame

# =========================================
# SHARED FRAME STATE (for stream server)
# =========================================
latest_frame_bytes = None
frame_lock = threading.Lock()

# =========================================
# STREAM SERVER
# =========================================
stream_app = Flask(__name__)

@stream_app.route("/stream")
def stream():
    def generate():
        while True:
            with frame_lock:
                frame = latest_frame_bytes
            if frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.033)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

def start_stream_server(port: int = 8080):
    import logging as _logging
    _logging.getLogger("werkzeug").setLevel(_logging.ERROR)
    stream_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)

# =========================================
# BACKGROUND MOTION THREAD
# =========================================
def motion_listener(motion_sensor, motion_event):
    """Waits for motion in the background so it doesn't freeze the camera."""
    while True:
        motion_sensor.wait_for_motion()
        motion_event.set()
        time.sleep(2) # Prevent rapid re-triggering

# =========================================
# ENTRY LOCKOUT (pause system after authorization)
# =========================================
DOOR_OPEN_TIMEOUT = 30  # seconds to wait for door to open before giving up

def entry_lockout_handler(door_sensor, speaker, logger, lockout_event):
    """
    Runs in a background thread after a face is authorized.
    Blocks motion detection + face recognition until:
      1. Door opens  (person walks in)
      2. Door closes (door is shut behind them)
    Falls back after DOOR_OPEN_TIMEOUT seconds if door never opens.
    """
    logger.info("[LOCKOUT] Entry authorized. Waiting for door to open (timeout: %ds)...", DOOR_OPEN_TIMEOUT)

    # Phase 1 — wait for door to open (with timeout)
    deadline = time.time() + DOOR_OPEN_TIMEOUT
    while not door_sensor.is_open():
        if time.time() > deadline:
            logger.warning("[LOCKOUT] Door never opened within timeout. Resuming system.")
            speaker.say("No entry detected. System re-armed.")
            lockout_event.clear()
            return
        time.sleep(0.1)

    logger.info("[LOCKOUT] Door opened. Waiting for door to close...")
    speaker.say("Welcome. Please close the door behind you.")

    # Phase 2 — wait for door to close
    while door_sensor.is_open():
        time.sleep(0.1)

    logger.info("[LOCKOUT] Door closed. Security system resuming.")
    speaker.say("Door secured. System re-armed.")
    lockout_event.clear()

# =========================================
# UNATTENDED DOOR WATCHER
# (independent of face recognition — catches "door open, nobody recognized")
# =========================================
UNATTENDED_DOOR_THRESHOLD = 30  # seconds door can be open with no authorized entry before alarming
UNATTENDED_DOOR_REPEAT    = 30  # seconds between repeated alarms while still unattended-open

def unattended_door_watcher(door_sensor, speaker, logger, lockout_event):
    """
    Runs continuously in its own background thread, completely independent
    of whether any face has ever been recognized. This is what catches the
    case a face-triggered alarm cannot: the door is open, but nobody was
    ever recognized in front of it (forced open, not latched shut, etc).

    While lockout_event is set (an authorized entry is in progress — see
    entry_lockout_handler), this watcher stays silent no matter how long
    the door is open, since that's an expected, already-explained state.

    Logs every door open/close transition to the CSV (event_type="door"),
    and additionally calls the speaker every UNATTENDED_DOOR_REPEAT seconds
    for as long as the door remains open past UNATTENDED_DOOR_THRESHOLD
    without an authorized entry in progress.

    BUGFIX, confirmed via real hardware testing: ALARM_FLAG_PATH used to
    only be checked ONCE PER ALARM CYCLE — i.e. only at the exact moment
    next_alarm_at fired, roughly every UNATTENDED_DOOR_REPEAT (~35s)
    seconds. Clicking "Stop Alert" on the dashboard wrote the flag file
    correctly and immediately (confirmed directly via curl), but this
    loop wouldn't actually LOOK at that file until the next scheduled
    alarm — meaning from the person's perspective, clicking the button
    appeared to do nothing for up to ~35 seconds. Now checks the flag on
    EVERY loop iteration (every 0.5s, same as the loop's own sleep), so
    a dismiss takes effect almost immediately — if it's present, it's
    consumed right away and next_alarm_at is pushed forward by the same
    REPEAT interval, exactly as if that alarm had already fired and been
    dismissed, without waiting for the actual scheduled time to arrive.
    """
    was_open          = False
    open_since         = None
    next_alarm_at      = None

    while True:
        is_open = door_sensor.is_open()

        # Check for a dashboard dismiss on EVERY iteration, not just when
        # next_alarm_at fires — this is the actual fix for the ~35s delay.
        # Only matters while an alarm cycle is actually pending (door
        # open, not in lockout); checking when there's nothing scheduled
        # would just silently consume a flag with no effect either way,
        # so it's gated the same way the alarm-check itself is.
        if is_open and not lockout_event.is_set() and next_alarm_at is not None:
            if os.path.exists(ALARM_FLAG_PATH):
                try:
                    os.remove(ALARM_FLAG_PATH)
                    logger.info("[DOOR-WATCH] Alarm dismissed via dashboard — pushing next alarm forward.")
                    next_alarm_at = time.time() + UNATTENDED_DOOR_REPEAT
                except Exception as e:
                    logger.error(f"[DOOR-WATCH] Failed to consume dismiss flag: {e}")

        if is_open and not was_open:
            # Door just transitioned closed -> open
            open_since    = time.time()
            next_alarm_at = open_since + UNATTENDED_DOOR_THRESHOLD
            write_log_row(logger, event_type="door", door_status="Open")
            logger.info("[DOOR-WATCH] Door opened.")

        elif not is_open and was_open:
            # Door just transitioned open -> closed
            write_log_row(logger, event_type="door", door_status="Closed")
            logger.info("[DOOR-WATCH] Door closed.")
            open_since    = None
            next_alarm_at = None

        elif is_open and not lockout_event.is_set():
            # Door has been continuously open; check if it's unattended too long
            if next_alarm_at is not None and time.time() >= next_alarm_at:
                logger.warning(
                    "[DOOR-WATCH] Door open %ds with no authorized entry — ALARM",
                    int(time.time() - open_since),
                )
                speaker.say("Warning. Door has been left open. Please check the entrance.")
                write_log_row(
                    logger, event_type="door",
                    threat_level="Suspicious", door_status="Open",
                )
                next_alarm_at = time.time() + UNATTENDED_DOOR_REPEAT

        was_open = is_open
        time.sleep(0.5)

# =========================================
# MAIN
# =========================================
def main():
    # 1. Parse Command Line Arguments
    parser = argparse.ArgumentParser(description="Smart Security System")
    parser.add_argument(
        "--camera", 
        type=str, 
        choices=["auto", "webcam", "picamera2"], 
        default="auto",
        help="Choose the camera backend to use (default: auto)."
    )
    args = parser.parse_args()

    config = load_config()
    setup_logging(config["log_to_file"], config["log_file"])
    logger = logging.getLogger(__name__)

    logger.info("=== Smart Security System Starting ===")

    try:
        with open("logo.txt", "r") as f:
            print(f.read())
    except FileNotFoundError:
        pass

    from src.motion_sensor import MotionSensor
    from src.speaker import Speaker
    from src.face_recognition_engine import FaceRecognitionEngine
    from src.door_sensor import DoorSensor

    motion_sensor = MotionSensor(pin=config["gpio_pin"])
    speaker       = Speaker(language=config["tts_language"], speed=config["tts_speed"])
    door_sensor   = DoorSensor(pin=config["door_sensor_pin"])

    engine = FaceRecognitionEngine(
        known_faces_dir=KNOWN_FACES_DIR,
        models_dir=MODELS_DIR,
        tolerance=config.get("tolerance", 0.5),
        risk_medium_threshold=config.get("unknown_risk_medium_threshold", 3),
        risk_high_threshold=config.get("unknown_risk_high_threshold",   5),
    )

    if not engine.model_loaded:
        logger.warning(
            "No trained model found in '%s'. "
            "Run train_model.py to train one before faces can be recognised.",
            MODELS_DIR,
        )

    os.makedirs(STRANGERS_DIR, exist_ok=True)

    # 2. Initialize Camera with requested mode
    video_capture = Camera(config["camera_index"], mode=args.camera)
    camera_available = video_capture.isOpened()
    
    if not camera_available:
        if video_capture.init_error:
            logger.warning(video_capture.init_error)
        logger.warning("Running without camera — face recognition disabled.")
    else:
        logger.info(f"Camera ready (backend: {video_capture.backend})")

    frame_skip  = config["frame_skip"]
    frame_count = 0

    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    stream_port = config.get("stream_port", 8080)
    threading.Thread(target=start_stream_server, args=(stream_port,), daemon=True).start()
    logger.info(f"Stream server started on port {stream_port}")

    # Start the background motion detection thread
    motion_event = threading.Event()
    threading.Thread(target=motion_listener, args=(motion_sensor, motion_event), daemon=True).start()

    logger.info("System ready. Camera live 24/7. Waiting for motion to activate scanner...")

    scanning_active = False
    last_detection_time = 0
    # BUGFIX, confirmed via real-world testing: this was previously a
    # single global timestamp (last_stranger_save = 0), shared across
    # EVERY unrecognized face — meaning if Stranger A triggered a save,
    # a genuinely DIFFERENT Stranger B showing up within
    # STRANGER_SAVE_INTERVAL_SECONDS would be silently skipped entirely
    # (no photo, no CSV row, no popup), even though the speaker still
    # announced them. There's no real face-matching for unrecognized
    # people (every unknown face shares the literal name "Unknown" —
    # confirmed in face_recognition_engine.py), so true per-identity
    # tracking isn't available without building real embedding-based
    # matching (a separate, larger feature, deliberately not built here
    # per explicit scoping discussion). As an honest middle ground,
    # this keys the cooldown by rough screen LOCATION instead — each
    # detection's bounding box is rounded into a coarse grid cell, and
    # only saves matching THAT cell's own cooldown are skipped. Two
    # people standing in genuinely different parts of the frame get
    # independent cooldowns; the same lingering person moving slightly
    # still correctly maps to the same cell.
    last_stranger_save_by_location = {}
    current_results = []
    spoken_this_frame = set()
    entry_lockout = threading.Event()  # set = system paused waiting for door open+close
    last_system_heartbeat = 0  # throttle — see write_system_heartbeat() below

    # Start the independent door watcher (catches "open, nobody recognized")
    threading.Thread(
        target=unattended_door_watcher,
        args=(door_sensor, speaker, logger, entry_lockout),
        daemon=True,
    ).start()
    logger.info("Unattended door watcher started (threshold: %ds).", UNATTENDED_DOOR_THRESHOLD)

    try:
        while True:
            if not camera_available:
                time.sleep(1)
                continue

            # 1. ALWAYS READ THE CAMERA
            ret, frame = video_capture.read()
            if not ret or frame is None:
                logger.error("Failed to read from camera.")
                time.sleep(0.5)
                continue

            # System heartbeat — touched here, after a successful camera
            # read, NOT gated by motion/scanning state, so a stale
            # timestamp genuinely means the whole process is stuck or
            # dead, not just "nothing happened recently" (that distinction
            # already exists separately via last_event_time in pi_server.py).
            # Throttled to once every 5s (not every single frame) to avoid
            # excessive write wear on the Pi's SD card over a 24/7 runtime.
            now_hb = time.time()
            if now_hb - last_system_heartbeat > 5:
                try:
                    with open(SYSTEM_HEARTBEAT_PATH, "w") as hb:
                        json.dump({"last_alive": now_hb}, hb)
                    last_system_heartbeat = now_hb
                except Exception as e:
                    logger.error(f"[SYSTEM-HEARTBEAT] Failed to write: {e}")

            # 2. CHECK IF MOTION WAS DETECTED
            if motion_event.is_set():
                if entry_lockout.is_set():
                    # System is paused for entry — swallow the motion event silently
                    motion_event.clear()
                else:
                    logger.info("Motion detected — waking up Face Recognition Engine...")
                    speaker.say("Motion detected. Scanning.")
                    scanning_active = True
                    last_detection_time = time.time()
                    spoken_this_frame.clear()
                    motion_event.clear()

            # 3. RUN FACE RECOGNITION (Only if scanning is active and not in entry lockout)
            frame_to_display = frame.copy()

            if scanning_active and not entry_lockout.is_set():
                frame_count += 1
                
                # Only process heavy AI on skipped frames to keep video smooth
                if frame_count % frame_skip == 0:
                    small_frame     = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                    current_results = engine.process_frame(rgb_small_frame)

                    for result in current_results:
                        voice = result["voice"]
                        if voice not in spoken_this_frame:
                            speaker.say(voice)
                            spoken_this_frame.add(voice)

                        last_detection_time = time.time()
                        authorized = result["action"] == "AUTHORIZED"

                        # Only the CSV write is gated on a final outcome —
                        # door_sensor.handle_door_event() below runs for
                        # EVERY detected face, including VERIFYING and
                        # WAIT_LIVENESS. Reasoning: if the door is already
                        # open before identity is even confirmed, that's
                        # dangerous regardless of who's standing there —
                        # the alarm must fire immediately, not wait for a
                        # liveness check to finish. Logging is separate:
                        # VERIFYING/WAIT_LIVENESS are sub-second transient
                        # states, not real audit-log-worthy events, so they
                        # don't get a CSV row — but the door alarm still
                        # checks every single frame, no exceptions.
                        is_final_outcome = result["action"] in ("AUTHORIZED", "DENIED")

                        if is_final_outcome:
                            # Log this detection event to the CSV the dashboard reads.
                            # .get() used for keys not confirmed to always exist, so a
                            # missing field never crashes the live detection loop.
                            write_log_row(
                                logger,
                                event_type="visitor",
                                visitor_name=result["name"],
                                auth_result=result["action"],
                                threat_level=result.get("risk", ""),
                                door_status="Open" if door_sensor.is_open() else "Closed",
                                confidence=result.get("confidence", ""),
                            )

                        door_sensor.handle_door_event(
                            authorized=authorized,
                            name=result["name"],
                            speaker=speaker,
                            save_stranger_fn=save_stranger if not authorized else None,
                            frame=frame,
                            risk=result["risk"],
                        )

                        # Authorized entry — pause system until door opens and closes
                        if authorized and not entry_lockout.is_set():
                            logger.info("[LOCKOUT] %s authorized. Pausing system for entry.", result["name"])
                            entry_lockout.set()
                            scanning_active = False
                            current_results = []
                            threading.Thread(
                                target=entry_lockout_handler,
                                args=(door_sensor, speaker, logger, entry_lockout),
                                daemon=True,
                            ).start()
                            break  # stop processing other faces this frame

                        if result["action"] == "DENIED":
                            # Heartbeat write happens EVERY frame a stranger
                            # is detected, deliberately NOT gated by
                            # STRANGER_SAVE_INTERVAL_SECONDS below — that
                            # cooldown is specifically about not spamming
                            # new PHOTOS for the same lingering person,
                            # but presence itself needs updating as often
                            # as the detection loop actually runs, so
                            # "gone" can be detected within roughly one
                            # detection cycle of them actually leaving,
                            # not up to a full save-interval late.
                            # Wrapped in try/except since a failure to
                            # write this file should never crash the
                            # live detection loop over something this minor.
                            try:
                                with open(STRANGER_HEARTBEAT_PATH, "w") as hb:
                                    json.dump({"last_seen": time.time()}, hb)
                            except Exception as e:
                                logger.error(f"[HEARTBEAT] Failed to write: {e}")

                            now = time.time()
                            # Round the face's bounding box into a coarse
                            # grid cell (100px) — this is a deliberate
                            # approximation, not true identity matching:
                            # two clearly different people standing apart
                            # get different cells (independent cooldowns,
                            # confirmed fix for the silent-skip bug), but
                            # this can't distinguish two strangers who
                            # happen to stand in roughly the same spot
                            # one after another — that genuinely needs
                            # real face-embedding comparison, which was
                            # explicitly scoped out as a larger, separate
                            # feature in this same conversation.
                            top, right, bottom, left = result["location"]
                            cell_size = 100
                            location_key = (
                                round(top / cell_size),
                                round(left / cell_size),
                            )
                            last_saved_at = last_stranger_save_by_location.get(location_key, 0)

                            if now - last_saved_at > STRANGER_SAVE_INTERVAL_SECONDS:
                                saved_filename = save_stranger(frame, result["risk"], logger)
                                last_stranger_save_by_location[location_key] = now
                                if saved_filename:
                                    write_log_row(
                                        logger,
                                        event_type="visitor",
                                        visitor_name=result["name"],
                                        auth_result=result["action"],
                                        threat_level=result.get("risk", ""),
                                        door_status="Open" if door_sensor.is_open() else "Closed",
                                        confidence=result.get("confidence", ""),
                                        img_file=saved_filename,
                                    )

                # Draw the bounding boxes on the live feed
                frame_to_display = draw_results(frame_to_display, current_results, scale=2)

                # Check if it's time to go back to sleep
                if time.time() - last_detection_time > config["sleep_after_detection_seconds"]:
                    logger.info("No activity. Face scanner going to sleep. Camera remains live.")
                    scanning_active = False
                    current_results = [] # Clear boxes

            # 4. PUSH FRAME TO WEB APP
            ret_enc, buffer = cv2.imencode('.jpg', frame_to_display)
            if ret_enc:
                with frame_lock:
                    global latest_frame_bytes
                    latest_frame_bytes = buffer.tobytes()

            # 5. LOCAL DISPLAY (If connected to monitor)
            if has_display:
                cv2.imshow("Smart Security", frame_to_display)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    logger.info("Quit key pressed.")
                    raise KeyboardInterrupt

    except KeyboardInterrupt:
        logger.info("Shutting down.")

    finally:
        video_capture.release()
        if has_display:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass
        motion_sensor.cleanup()
        speaker.cleanup()
        door_sensor.cleanup()
        logger.info("=== Smart Security System Stopped ===")

if __name__ == "__main__":
    main()
