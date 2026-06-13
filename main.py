import cv2
import time
import json
import logging
import os
import sys
import threading
from flask import Flask, Response

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

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
KNOWN_FACES_DIR = os.environ.get("KNOWN_FACES_DIR", "known_faces")
STRANGERS_DIR = os.environ.get("STRANGERS_DIR", "strangers")

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

def draw_results(frame, results, scale: int = 4):
    for result in results:
        top, right, bottom, left = result["location"]
        top *= scale
        right *= scale
        bottom *= scale
        left *= scale

        color = (0, 255, 0) if result["action"] == "AUTHORIZED" else (0, 0, 255)
        label = f"{result['name']} | {result['risk']}"

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
        cv2.putText(frame, label, (left + 6, bottom - 6),
                    cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)

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
    _logging.getLogger("werkzeug").setLevel(_logging.ERROR)  # silence Flask logs
    stream_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

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
    speaker = Speaker(language=config["tts_language"], speed=config["tts_speed"])
    door_sensor = DoorSensor(pin=config["door_sensor_pin"])
    engine = FaceRecognitionEngine(
        known_faces_dir=KNOWN_FACES_DIR,
        tolerance=config["tolerance"],
        risk_medium_threshold=config["unknown_risk_medium_threshold"],
        risk_high_threshold=config["unknown_risk_high_threshold"]
    )

    # Ensure strangers folder exists
    os.makedirs(STRANGERS_DIR, exist_ok=True)

    video_capture = cv2.VideoCapture(config["camera_index"])
    camera_available = video_capture.isOpened()
    if not camera_available:
        logger.warning("No camera found. Running without camera — face recognition disabled.")

    frame_skip = config["frame_skip"]
    frame_count = 0

    # Detect if a display is available (headless guard)
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    # Start stream server in background thread
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
            last_stranger_save = 0   # throttle saves to once per 10s per event

            # =====================================
            # RECOGNITION LOOP (active after motion)
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

                small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
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
                        risk=result["risk"]
                    )

                    # =====================================
                    # SAVE STRANGER IMAGE
                    # =====================================

                    if result["action"] == "DENIED":
                        now = time.time()
                        # Throttle: save at most once every 10 seconds
                        if now - last_stranger_save > 10:
                            save_stranger(frame, result["risk"], logger)
                            last_stranger_save = now

                # =====================================
                # DRAW & DISPLAY
                # =====================================

                annotated = draw_results(frame, results)

                # Push annotated frame to stream server
                ret_enc, buffer = cv2.imencode('.jpg', annotated)
                if ret_enc:
                    with frame_lock:
                        latest_frame_bytes = buffer.tobytes()

                # Only show window if a display is available
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