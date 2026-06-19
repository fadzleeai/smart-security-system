import cv2
import time
import json
import logging
import os
import sys
import threading
from flask import Flask, Response

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except (ImportError, RuntimeError):
    PICAMERA2_AVAILABLE = False

# =========================================
# CAMERA ADAPTER
# =========================================
# Pi Camera Module (v2/v3, CSI) needs picamera2 — cv2.VideoCapture cannot
# reliably read frames from libcamera-backed sensors on current Pi OS.
# Falls back to cv2.VideoCapture for USB webcams / non-Pi dev machines.

class Camera:

    def __init__(self, camera_index: int, width: int = 640, height: int = 480):
        self.backend = None
        self._picam = None
        self._cv_cap = None
        self.init_error = None

        if PICAMERA2_AVAILABLE:
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
                self.init_error = exc
                self._picam = None

        if self.backend is None:
            self._cv_cap = cv2.VideoCapture(camera_index)
            if self._cv_cap.isOpened():
                self.backend = "cv2"

    def isOpened(self) -> bool:
        return self.backend is not None

    def read(self):
        """Returns (ret, frame) as BGR, matching cv2.VideoCapture.read()."""
        if self.backend == "picamera2":
            try:
                frame_rgb = self._picam.capture_array()
                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                return True, frame_bgr
            except Exception:
                return False, None
        elif self.backend == "cv2":
            return self._cv_cap.read()
        return False, None

    def release(self):
        if self.backend == "picamera2" and self._picam is not None:
            try:
                self._picam.stop()
            except Exception:
                pass
        elif self.backend == "cv2" and self._cv_cap is not None:
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

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

# =========================================
# SAVE STRANGER IMAGE
# =========================================

def save_stranger(frame, risk: str, logger):
    try:
        os.makedirs(STRANGERS_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{STRANGERS_DIR}/stranger_{timestamp}_{risk}.jpg"
        cv2.imwrite(filename, frame)
        logger.info(f"Stranger image saved: {filename}")
    except Exception as e:
        logger.error(f"Failed to save stranger image: {e}")

# =========================================
# DRAW RESULTS ON FRAME
# =========================================

def draw_results(frame, results, scale: int = 2):
    """
    Draw bounding boxes and labels for each result.
    scale=2 because the engine now uses FRAME_SCALE=0.5 (was 0.25 before).
    """
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
            color = (0, 165, 255)   # orange for VERIFYING / WAIT_LIVENESS

        name      = result["name"]
        risk      = result.get("risk", "")
        liveness  = result.get("liveness", "")
        conf      = result.get("confidence", 0.0)

        lines = [
            f"{name} | {action}",
            f"Risk: {risk} | Conf: {conf:.0%}",
            f"Liveness: {liveness}",
        ]

        # background panel above the box
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
# MAIN
# =========================================

def main():
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
        tolerance=config.get("tolerance", 0.5),            # kept for compat
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

    video_capture    = Camera(config["camera_index"])
    camera_available = video_capture.isOpened()
    if not camera_available:
        logger.warning("No camera found. Running without camera — face recognition disabled.")
    else:
        logger.info(f"Camera ready (backend: {video_capture.backend})")
        if video_capture.backend == "cv2" and video_capture.init_error is not None:
            logger.warning(f"picamera2 init failed, fell back to cv2: {video_capture.init_error}")

    frame_skip  = config["frame_skip"]
    frame_count = 0

    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    stream_port = config.get("stream_port", 8080)
    threading.Thread(target=start_stream_server, args=(stream_port,), daemon=True).start()
    logger.info(f"Stream server started on port {stream_port}")

    logger.info("System ready. Waiting for motion...")

    try:
        while True:

            # =====================================
            # WAIT FOR MOTION
            # =====================================

            motion_sensor.wait_for_motion()

            logger.info("Motion detected — activating camera...")
            speaker.say("Motion detected. Scanning.")

            time.sleep(config["camera_warmup_seconds"])

            last_detection_time = time.time()
            last_stranger_save  = 0

            # =====================================
            # RECOGNITION LOOP
            # =====================================

            if not camera_available:
                logger.warning("Camera not connected — skipping face recognition.")
                time.sleep(config["sleep_after_detection_seconds"])
                continue

            while True:
                ret, frame = video_capture.read()
                if not ret:
                    logger.error("Failed to read from camera.")
                    break

                frame_count += 1
                if frame_count % frame_skip != 0:
                    continue

                # engine uses FRAME_SCALE=0.5 internally; draw_results uses scale=2
                small_frame     = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                results = engine.process_frame(rgb_small_frame)

                # =====================================
                # HANDLE RESULTS
                # =====================================

                spoken_this_frame = set()

                for result in results:
                    voice = result["voice"]

                    if voice not in spoken_this_frame:
                        speaker.say(voice)
                        spoken_this_frame.add(voice)

                    last_detection_time = time.time()

                    # =====================================
                    # DOOR SENSOR LOGIC
                    # =====================================

                    authorized = result["action"] == "AUTHORIZED"
                    door_sensor.handle_door_event(
                        authorized=authorized,
                        name=result["name"],
                        speaker=speaker,
                        save_stranger_fn=save_stranger if not authorized else None,
                        frame=frame,
                        risk=result["risk"],
                    )

                    # =====================================
                    # SAVE STRANGER IMAGE
                    # =====================================

                    if result["action"] == "DENIED":
                        now = time.time()
                        if now - last_stranger_save > 10:
                            save_stranger(frame, result["risk"], logger)
                            last_stranger_save = now

                # =====================================
                # DRAW & DISPLAY / STREAM
                # =====================================

                annotated = draw_results(frame, results, scale=2)

                ret_enc, buffer = cv2.imencode('.jpg', annotated)
                if ret_enc:
                    with frame_lock:
                        latest_frame_bytes = buffer.tobytes()

                if has_display:
                    cv2.imshow("Smart Security", annotated)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        logger.info("Quit key pressed.")
                        raise KeyboardInterrupt

                # =====================================
                # SLEEP IF NO DETECTION FOR A WHILE
                # =====================================

                if time.time() - last_detection_time > config["sleep_after_detection_seconds"]:
                    logger.info("No activity. Going back to sleep.")
                    if has_display:
                        try:
                            cv2.destroyAllWindows()
                        except cv2.error:
                            pass
                    break

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