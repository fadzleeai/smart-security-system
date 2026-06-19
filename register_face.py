"""
register_face.py — capture face samples via webcam and save them to known_faces/.

Run this from the project root:
    python register_face.py

After adding new faces, run train_model.py to retrain the classifier.
"""

import os
import sys

import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.embedding_engine import MODEL_FILENAMES


KNOWN_FACES_DIR    = os.path.join(BASE_DIR, "known_faces")
MODELS_DIR         = os.path.join(BASE_DIR, "models")
IMAGE_EXTENSIONS   = (".jpg", ".jpeg", ".png")
DEFAULT_SAMPLE_COUNT = 10
MIN_FACE_SIZE      = 80
BLUR_THRESHOLD     = 50.0


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


def main():
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

    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print("Error: webcam could not be opened.")
        return

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    captured_count = 0
    stopped_early  = False
    model_invalidation_attempted = False

    print("Camera opened.")
    print("Keep one face visible and press SPACE to capture.")
    print("Press Q to quit.")

    try:
        while captured_count < target_count:
            success, frame = camera.read()
            if not success:
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
        cv2.destroyAllWindows()

    if captured_count >= target_count:
        print_completion_summary(person_name, captured_count)
    elif stopped_early:
        print_early_stop_summary(captured_count)


if __name__ == "__main__":
    main()