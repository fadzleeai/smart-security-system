import cv2
import time
import json
import logging
import os
import sys

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

    motion_sensor = MotionSensor(pin=config["gpio_pin"])
    speaker = Speaker(language=config["tts_language"], speed=config["tts_speed"])
    engine = FaceRecognitionEngine(
        known_faces_dir=KNOWN_FACES_DIR,
        tolerance=config["tolerance"],
        risk_medium_threshold=config["unknown_risk_medium_threshold"],
        risk_high_threshold=config["unknown_risk_high_threshold"]
    )

    # Ensure strangers folder exists
    os.makedirs(STRANGERS_DIR, exist_ok=True)

    video_capture = cv2.VideoCapture(config["camera_index"])
    frame_skip = config["frame_skip"]
    frame_count = 0

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
                cv2.imshow("Smart Security", annotated)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    logger.info("Quit key pressed.")
                    raise KeyboardInterrupt

                # =====================================
                # SLEEP IF NO DETECTION FOR A WHILE
                # =====================================

                if time.time() - last_detection_time > config["sleep_after_detection_seconds"]:
                    logger.info("No activity. Going back to sleep.")
                    cv2.destroyAllWindows()
                    break

    except KeyboardInterrupt:
        logger.info("Shutting down.")

    finally:
        video_capture.release()
        cv2.destroyAllWindows()
        motion_sensor.cleanup()
        speaker.cleanup()
        logger.info("=== Smart Security System Stopped ===")


if __name__ == "__main__":
    main()