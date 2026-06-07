import os
import numpy as np
import face_recognition
import logging

logger = logging.getLogger(__name__)


class FaceRecognitionEngine:

    def __init__(self, known_faces_dir: str, tolerance: float = 0.5,
                 risk_medium_threshold: int = 3, risk_high_threshold: int = 5):

        self.known_faces_dir = known_faces_dir
        self.tolerance = tolerance
        self.risk_medium_threshold = risk_medium_threshold
        self.risk_high_threshold = risk_high_threshold

        self.known_face_encodings = []
        self.known_face_names = []
        self.unknown_counter = 0

        self.load_known_faces()

    # =========================================
    # LOAD KNOWN FACES
    # =========================================

    def load_known_faces(self):
        self.known_face_encodings = []
        self.known_face_names = []

        if not os.path.exists(self.known_faces_dir):
            logger.warning(f"known_faces directory not found: {self.known_faces_dir}")
            return

        logger.info("Loading authorized faces...")

        for filename in os.listdir(self.known_faces_dir):
            if filename.lower().endswith((".jpg", ".png")):
                image_path = os.path.join(self.known_faces_dir, filename)
                try:
                    image = face_recognition.load_image_file(image_path)
                    encodings = face_recognition.face_encodings(image)

                    if encodings:
                        self.known_face_encodings.append(encodings[0])
                        name = os.path.splitext(filename)[0]
                        self.known_face_names.append(name)
                        logger.info(f"  Loaded: {name}")
                    else:
                        logger.warning(f"  No face found in {filename}, skipping.")

                except Exception as e:
                    logger.error(f"  Failed to load {filename}: {e}")

        logger.info(f"Dataset ready. {len(self.known_face_names)} face(s) loaded.")

    # =========================================
    # RECOGNIZE FACE
    # =========================================

    def recognize_face(self, face_encoding) -> tuple[str, float]:
        if not self.known_face_encodings:
            return "Unknown", 1.0

        distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
        best_match_index = np.argmin(distances)
        best_distance = distances[best_match_index]

        if best_distance < self.tolerance:
            name = self.known_face_names[best_match_index]
            confidence = 1 - best_distance
            return name, confidence

        return "Unknown", 1 - best_distance

    # =========================================
    # RISK SYSTEM
    # =========================================

    def update_risk(self, name: str) -> tuple[int, str]:
        if name == "Unknown":
            self.unknown_counter += 1
            count = self.unknown_counter

            if count < self.risk_medium_threshold:
                risk = "Low"
            elif count < self.risk_high_threshold:
                risk = "Medium"
            else:
                risk = "HIGH"

            return count, risk
        else:
            self.unknown_counter = 0
            return 0, "Safe"

    # =========================================
    # DECISION ENGINE
    # =========================================

    def process_frame(self, rgb_frame) -> list[dict]:
        face_locations = face_recognition.face_locations(rgb_frame, model="hog")
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        results = []

        for encoding, location in zip(face_encodings, face_locations):
            name, confidence = self.recognize_face(encoding)
            count, risk = self.update_risk(name)

            if name != "Unknown":
                result = {
                    "name": name,
                    "confidence": round(confidence, 2),
                    "action": "AUTHORIZED",
                    "risk": "Safe",
                    "location": location,
                    "voice": f"Welcome, {name}"
                }
            else:
                if risk == "HIGH":
                    voice = "Security alert activated. Please leave the area."
                else:
                    voice = "Access denied. Owner has been notified."

                result = {
                    "name": "Unknown",
                    "confidence": round(confidence, 2),
                    "action": "DENIED",
                    "risk": risk,
                    "unknown_count": count,
                    "location": location,
                    "voice": voice
                }

            results.append(result)
            logger.info(f"{result['name']} | {result['action']} | {result['risk']}")

        return results
