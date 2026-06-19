import cv2
import face_recognition
import os
import json
import time

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except (ImportError, RuntimeError):
    PICAMERA2_AVAILABLE = False

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
KNOWN_FACES_DIR = os.environ.get("KNOWN_FACES_DIR", "known_faces")

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

# =========================================
# CAMERA ADAPTER
# =========================================
# Shared from main.py to handle Pi 5 picamera2 compatibility
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
# MAIN
# =========================================
def main():
    config = load_config()
    os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

    name = input("Enter person's name: ").strip()
    if not name:
        print("Name cannot be empty.")
        return

    print("\nInitializing camera...")
    video_capture = Camera(config["camera_index"])
    
    if not video_capture.isOpened():
        print("Error: Could not open camera.")
        return

    print(f"\nCamera opened (Backend: {video_capture.backend}).")
    print("Click on the camera window first, then:")
    print("Press SPACE to save face.")
    print("Press Q to quit.\n")

    while True:
        ret, frame = video_capture.read()
        if not ret or frame is None:
            print("Failed to read frame.")
            break

        display = frame.copy()
        cv2.putText(display, "Click window first! SPACE = save  Q = quit",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.imshow("Register Face", display)

        key = cv2.waitKey(1) & 0xFF

        if key == 32:  # SPACE
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)

            if face_locations:
                file_path = os.path.join(KNOWN_FACES_DIR, f"{name}.jpg")
                cv2.imwrite(file_path, frame)
                print(f"Face saved successfully -> {file_path}")
                break
            else:
                print("No face detected. Reposition and try again.")
                continue

        elif key == ord('q'):
            print("Quit.")
            break

        try:
            if cv2.getWindowProperty("Register Face", cv2.WND_PROP_VISIBLE) < 1:
                break
        except Exception:
            break

    video_capture.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()