import cv2
import face_recognition
import os
import json

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
KNOWN_FACES_DIR = os.environ.get("KNOWN_FACES_DIR", "known_faces")

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def main():
    config = load_config()
    os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

    name = input("Enter person's name: ").strip()
    if not name:
        print("Name cannot be empty.")
        return

    video_capture = cv2.VideoCapture(config["camera_index"])

    print("\nCamera opened.")
    print("Click on the camera window first, then:")
    print("Press SPACE to save face.")
    print("Press Q to quit.\n")

    while True:
        ret, frame = video_capture.read()
        if not ret:
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
