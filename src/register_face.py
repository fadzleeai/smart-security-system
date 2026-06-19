"""
register_face.py — capture face samples via webcam and save them to known_faces/.

Run this from the project root:
    python register_face.py --camera webcam

After adding new faces, run train_model.py to retrain the classifier.
"""

import os
import sys
import cv2
import time
import json
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.embedding_engine import MODEL_FILENAMES

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except (ImportError, RuntimeError):
    PICAMERA2_AVAILABLE = False


KNOWN_FACES_DIR    = os.path.join(BASE_DIR, "known_faces")
MODELS_DIR         = os.path.join(BASE_DIR, "models")
CONFIG_PATH        = os.environ.get("CONFIG_PATH", os.path.join(BASE_DIR, "config.json"))
IMAGE_EXTENSIONS   = (".jpg", ".jpeg", ".png")
DEFAULT_SAMPLE_COUNT = 10
MIN_FACE_SIZE      = 80
BLUR_THRESHOLD     = 50.0

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
# HELPER FUNCTIONS
# =========================================
def clean_person_name(name):
    cleaned = name.strip().replace("/", "_").replace("\\", "_")
    return cleaned.strip(" .")

def sample_number_from_filename(filename, person_name):
    if not filename.lower().endswith(IMAGE_EXTENSIONS):
        return None
    stem = os.path.splitext(filename)[0]
    prefix = person_name + "_"
    if not stem.startswith(prefix):
        return None
    suffix = stem[len(prefix):]
    return int(suffix) if suffix.isdigit() else None

def person_sample_numbers(person_name):
    numbers = []
    for filename in os.listdir(KNOWN_FACES_DIR):
        number = sample_number_from_filename(filename, person_name)
        if number is not None:
            numbers.append(number)
    return numbers

def next_image_path(person_name):
    numbers = person_sample_numbers(person_name)
    next_number = max(numbers, default=0) + 1
    return os.path.join(
        KNOWN_FACES_DIR,
        "{}_{}.jpg".format(person_name, next_number),
    )

def count_person_images(person_name):
    return len(person_sample_numbers(person_name))

def ask_sample_count():
    while True:
        response = input(
            "How many samples to capture? Default {}: ".format(DEFAULT_SAMPLE_COUNT)
        ).strip()
        if not response:
            return DEFAULT_SAMPLE_COUNT
        try:
            sample_count = int(response)
        except ValueError:
            print("Please enter a positive whole number.")
            continue
        if sample_count <= 0:
            print("Please enter a positive whole number.")
            continue
        return sample_count

def crop_with_padding(frame, face_box):
    x, y, width, height = face_box
    pad_x = int(width * 0.20)
    pad_y = int(height * 0.20)
    left   = max(0, x - pad_x)
    top    = max(0, y - pad_y)
    right  = min(frame.shape[1], x + width + pad_x)
    bottom = min(frame.shape[0], y + height + pad_y)
    return frame[top:bottom, left:right]

def blur_score(face_image):
    gray_crop = cv2.cvtColor(face_image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())

def invalidate_trained_models():
    removed, failures = [], []
    for filename in MODEL_FILENAMES.values():
        path = os.path.join(MODELS_DIR, filename)
        if not os.path.isfile(path):
            continue
        try:
            os.remove(path)
            removed.append(filename)
        except OSError as error:
            failures.append((filename, error))
    return removed, failures

def print_variation_reminder(captured_count):
    reminders = {
        1: "Captured front face. Please slightly turn left/right for the next sample.",
        3: "Try different lighting or distance.",
        5: "Try a neutral or smiling expression.",
    }
    reminder = reminders.get(captured_count)
    if reminder:
        print(reminder)

def draw_preview(preview, faces, person_name, captured_count, target_count):
    for x, y, width, height in faces:
        cv2.rectangle(preview, (x, y), (x + width, y + height), (0, 255, 0), 2)

    lines = [
        "Name: {}".format(person_name),
        "Captured: {} / {}".format(captured_count, target_count),
        "Press SPACE to capture",
        "Press Q to quit",
    ]
    panel_height = 16 + len(lines) * 26
    cv2.rectangle(preview, (8, 8), (330, panel_height), (0, 0, 0), cv2.FILLED)
    for index, line in enumerate(lines):
        cv2.putText(
            preview, line,
            (18, 34 + index * 26),
            cv2.FONT_HERSHEY_DUPLEX, 0.58,
            (255, 255, 255), 1, cv2.LINE_AA,
        )

def print_completion_summary(person_name, captured_count):
    print("Registration completed.")
    print("Person:", person_name)
    print("Samples captured this session:", captured_count)
    print("Total saved images for this person:", count_person_images(person_name))
    print("Please run train_model.py to update the embedding classifier.")

def print_early_stop_summary(captured_count):
    print("Registration stopped early.")
    print("Samples captured this session:", captured_count)
    print("Please run train_model.py if new samples were added.")

# =========================================
# MAIN
# =========================================
def main():
    parser = argparse.ArgumentParser(description="Capture faces for Smart Security System")
    parser.add_argument(
        "--camera", 
        type=str, 
        choices=["auto", "webcam", "picamera2"], 
        default="auto",
        help="Choose the camera backend to use (default: auto)."
    )
    args = parser.parse_args()

    os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)

    person_name = clean_person_name(input("Enter person's name: "))
    if not person_name:
        print("A valid name is required.")
        return

    target_count = ask_sample_count()

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        print("Haar Cascade could not be loaded:", cascade_path)
        return

    # Load camera index from config.json to match main.py
    camera_index = 0
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            camera_index = config.get("camera_index", 0)

    print(f"\nInitializing camera (Index: {camera_index}, Mode: {args.camera})...")
    camera = Camera(camera_index=camera_index, mode=args.camera)
    
    if not camera.isOpened():
        print(f"Error: camera could not be opened. {camera.init_error}")
        return

    captured_count = 0
    stopped_early  = False
    model_invalidation_attempted = False

    print(f"Camera opened (Backend: {camera.backend}).")
    print("Keep one face visible and press SPACE to capture.")
    print("Press Q to quit.\n")

    try:
        while captured_count < target_count:
            success, frame = camera.read()
            if not success or frame is None:
                print("Camera frame could not be read.")
                stopped_early = True
                break

            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5,
                minSize=(MIN_FACE_SIZE, MIN_FACE_SIZE),
            )

            preview = frame.copy()
            draw_preview(preview, faces, person_name, captured_count, target_count)
            cv2.imshow("Register Multiple Face Samples", preview)

            key = cv2.waitKey(1) & 0xFF
            if key == 32:   # SPACE
                if len(faces) == 0:
                    print("No face detected. Adjust your position and try again.")
                    continue
                if len(faces) > 1:
                    print("Multiple faces detected. Keep only one face visible.")
                    continue

                x, y, width, height = faces[0]
                if width < MIN_FACE_SIZE or height < MIN_FACE_SIZE:
                    print("Face is too small. Move closer to the camera and try again.")
                    continue

                face_image = crop_with_padding(frame, faces[0])
                if face_image.size == 0 or (
                    face_image.shape[0] < MIN_FACE_SIZE
                    or face_image.shape[1] < MIN_FACE_SIZE
                ):
                    print("Face crop failed or too small. Please try again.")
                    continue

                if blur_score(face_image) < BLUR_THRESHOLD:
                    print("Image too blurry. Please hold still and try again.")
                    continue

                output_path = next_image_path(person_name)
                if not cv2.imwrite(output_path, face_image):
                    print("Face image could not be saved. Please try again.")
                    continue

                captured_count += 1
                print("Captured sample {}/{}: {}".format(
                    captured_count, target_count, output_path,
                ))

                if not model_invalidation_attempted:
                    _, failures = invalidate_trained_models()
                    model_invalidation_attempted = True
                    for filename, error in failures:
                        print("Warning: could not remove {}: {}".format(filename, error))
                    if not failures:
                        print(
                            "Old trained model files were removed. "
                            "Please run train_model.py again."
                        )

                print_variation_reminder(captured_count)

            elif key == ord("q"):
                stopped_early = True
                break
    finally:
        camera.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass

    if captured_count >= target_count:
        print_completion_summary(person_name, captured_count)
    elif stopped_early:
        print_early_stop_summary(captured_count)

if __name__ == "__main__":
    main()