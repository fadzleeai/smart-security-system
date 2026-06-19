"""
FaceRecognitionEngine — embedding-based drop-in replacement.

Replaces the old face_distance approach with:
  - 128-D softmax classifier + centroid gating  (embedding_engine.py)
  - Per-face vote window for stable identity     (VOTE_WINDOW frames)
  - Blink liveness check before AUTHORIZED       (face_test.py logic)
  - Event-based unknown risk counter             (not per-frame)

public interface (unchanged for main.py):
    engine = FaceRecognitionEngine(known_faces_dir, models_dir, ...)
    engine.load_model()           # call after train_model.py finishes
    results = engine.process_frame(rgb_frame)
    # each result dict contains: name, action, risk, voice, location,
    #   confidence, liveness, blink_count, unknown_count
"""

import logging
import os
import pickle
import time
from collections import Counter, deque

import face_recognition
import numpy as np

from src.embedding_engine import load_model_bundle, predict_embedding

logger = logging.getLogger(__name__)

# ── tunables ──────────────────────────────────────────────────────────────────
VOTE_WINDOW               = 5      # frames kept in rolling vote buffer
MIN_VOTES                 = 3      # votes needed for a stable identity
TRACK_MAX_DISTANCE        = 80     # px (scaled frame) to re-assign a tracker
TRACK_TIMEOUT_SECONDS     = 2.0    # drop tracker after this many idle seconds
BLINK_EAR_THRESHOLD       = 0.20   # eye-aspect-ratio below this = closed
BLINK_CLOSED_FRAMES       = 1      # consecutive closed frames = one blink
UNKNOWN_EVENT_GAP_SECONDS     = 2.0
UNKNOWN_EVENT_COOLDOWN_SECONDS = 8.0
RISK_MEDIUM_THRESHOLD     = 3
RISK_HIGH_THRESHOLD       = 5


# ── helpers ───────────────────────────────────────────────────────────────────

def _face_center(box):
    x, y, w, h = box
    return (x + w // 2, y + h // 2)


def _location_to_box(location):
    top, right, bottom, left = location
    return (int(left), int(top), int(right - left), int(bottom - top))


def _box_to_location(box):
    x, y, w, h = box
    return (y, x + w, y + h, x)


def _eye_aspect_ratio(points):
    if len(points) < 6:
        return None
    v1 = np.linalg.norm(np.asarray(points[1]) - np.asarray(points[5]))
    v2 = np.linalg.norm(np.asarray(points[2]) - np.asarray(points[4]))
    h  = np.linalg.norm(np.asarray(points[0]) - np.asarray(points[3]))
    return float((v1 + v2) / (2.0 * h)) if h else None


def _risk_label(count):
    if count < RISK_MEDIUM_THRESHOLD:
        return "Low"
    if count < RISK_HIGH_THRESHOLD:
        return "Medium"
    return "HIGH"


# ── tracker factory ───────────────────────────────────────────────────────────

def _new_tracker(track_id, box, now):
    return {
        "id":                   track_id,
        "box":                  box,
        "center":               _face_center(box),
        "last_seen":            now,
        "votes":                deque(maxlen=VOTE_WINDOW),
        "model_confidences":    deque(maxlen=VOTE_WINDOW),
        "centroid_distances":   deque(maxlen=VOTE_WINDOW),
        "closed_frames":        0,
        "blink_count":          0,
        "liveness_passed":      False,
        "liveness_name":        None,
        "ear":                  None,
        "last_print_signature": None,
    }


# ── main engine ───────────────────────────────────────────────────────────────

class FaceRecognitionEngine:

    def __init__(
        self,
        known_faces_dir: str,
        models_dir: str,
        tolerance: float = 0.5,           # kept for API compat, unused
        risk_medium_threshold: int = RISK_MEDIUM_THRESHOLD,
        risk_high_threshold: int  = RISK_HIGH_THRESHOLD,
    ):
        self.known_faces_dir       = known_faces_dir
        self.models_dir            = models_dir
        self.risk_medium_threshold = risk_medium_threshold
        self.risk_high_threshold   = risk_high_threshold

        self._model_bundle  = None
        self._trackers      = {}
        self._next_track_id = 1
        self._unknown_state = {
            "active":       False,
            "last_seen":    0.0,
            "last_counted": 0.0,
            "count":        0,
        }

        self.load_model()

    # ── model loading ─────────────────────────────────────────────────────────

    def load_model(self):
        """Load (or reload) the trained embedding classifier from disk."""
        try:
            self._model_bundle = load_model_bundle(self.models_dir)
            meta = self._model_bundle["metadata"]
            logger.info(
                "Embedding classifier loaded. Classes: %s | "
                "threshold: conf>=%.0f%% dist<=%.4f",
                meta.get("classes", []),
                float(meta["probability_threshold"]) * 100,
                float(meta["centroid_distance_threshold"]),
            )
        except (OSError, EOFError, pickle.PickleError, AttributeError, ValueError) as exc:
            logger.warning(
                "No trained model found (%s). "
                "Run train_model.py then call engine.load_model().", exc
            )
            self._model_bundle = None

    @property
    def model_loaded(self) -> bool:
        return self._model_bundle is not None

    # ── tracker management ────────────────────────────────────────────────────

    def _assign_trackers(self, boxes, now):
        # expire stale trackers
        stale = [
            tid for tid, t in self._trackers.items()
            if now - t["last_seen"] > TRACK_TIMEOUT_SECONDS
        ]
        for tid in stale:
            del self._trackers[tid]

        assignments = []
        used = set()

        for box in boxes:
            center = _face_center(box)
            best_tid, best_dist = None, float("inf")

            for tid, tracker in self._trackers.items():
                if tid in used:
                    continue
                dist = float(np.hypot(
                    center[0] - tracker["center"][0],
                    center[1] - tracker["center"][1],
                ))
                if dist <= TRACK_MAX_DISTANCE and dist < best_dist:
                    best_tid, best_dist = tid, dist

            if best_tid is None:
                best_tid = self._next_track_id
                self._next_track_id += 1
                self._trackers[best_tid] = _new_tracker(best_tid, box, now)

            t = self._trackers[best_tid]
            t["box"], t["center"], t["last_seen"] = box, center, now
            used.add(best_tid)
            assignments.append(best_tid)

        return assignments

    # ── voting helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _voted_identity(tracker):
        if not tracker["votes"]:
            return "Unknown", 0, False
        name, count = Counter(tracker["votes"]).most_common(1)[0]
        stable = (len(tracker["votes"]) == VOTE_WINDOW) and (count >= MIN_VOTES)
        return name, count, stable

    @staticmethod
    def _voted_scores(tracker, voted_name):
        pairs = [
            (c, d)
            for n, c, d in zip(
                tracker["votes"],
                tracker["model_confidences"],
                tracker["centroid_distances"],
            )
            if n == voted_name
        ]
        if not pairs:
            return 0.0, float("inf")
        return (
            float(np.mean([p[0] for p in pairs])),
            float(np.mean([p[1] for p in pairs])),
        )

    # ── liveness ──────────────────────────────────────────────────────────────

    def _update_blink(self, tracker, landmarks):
        left  = landmarks.get("left_eye")
        right = landmarks.get("right_eye")
        if not left or not right:
            return
        l_ear = _eye_aspect_ratio(left)
        r_ear = _eye_aspect_ratio(right)
        if l_ear is None or r_ear is None:
            return

        ear = (l_ear + r_ear) / 2.0
        tracker["ear"] = ear

        if ear < BLINK_EAR_THRESHOLD:
            tracker["closed_frames"] += 1
        else:
            if tracker["closed_frames"] >= BLINK_CLOSED_FRAMES:
                tracker["blink_count"] += 1
                tracker["liveness_passed"] = True
            tracker["closed_frames"] = 0

    # ── unknown risk ──────────────────────────────────────────────────────────

    def _update_unknown_event(self, unknown_present, now):
        state = self._unknown_state
        if unknown_present:
            if not state["active"]:
                cooldown_ok = (
                    state["last_counted"] == 0.0
                    or now - state["last_counted"] >= UNKNOWN_EVENT_COOLDOWN_SECONDS
                )
                if cooldown_ok:
                    state["count"] += 1
                    state["last_counted"] = now
            state["active"]    = True
            state["last_seen"] = now
        elif state["active"] and now - state["last_seen"] >= UNKNOWN_EVENT_GAP_SECONDS:
            state["active"] = False

        return state["count"], _risk_label(state["count"])

    # ── result builder ────────────────────────────────────────────────────────

    def _build_result(self, tracker, unknown_count, unknown_risk):
        name, vote_count, stable = self._voted_identity(tracker)
        confidence, centroid_dist = self._voted_scores(tracker, name)

        # ── still collecting votes ────────────────────────────────────────────
        if not stable:
            return {
                "name":             name if vote_count >= MIN_VOTES else "Checking",
                "action":           "VERIFYING",
                "risk":             "Pending",
                "confidence":       round(confidence, 2),
                "centroid_distance": round(centroid_dist, 3),
                "liveness":         "NOT_STARTED",
                "blink_count":      tracker["blink_count"],
                "unknown_count":    unknown_count,
                "location":         _box_to_location(tracker["box"]),
                "voice":            "Verifying visitor.",
            }

        # ── confirmed unknown ─────────────────────────────────────────────────
        if name == "Unknown":
            voice = (
                "Security alert activated. Please leave the area."
                if unknown_risk == "HIGH"
                else "Access denied. Owner has been notified."
            )
            return {
                "name":             "Unknown",
                "action":           "DENIED",
                "risk":             unknown_risk,
                "confidence":       round(confidence, 2),
                "centroid_distance": round(centroid_dist, 3),
                "liveness":         "NOT_REQUIRED",
                "blink_count":      0,
                "unknown_count":    unknown_count,
                "location":         _box_to_location(tracker["box"]),
                "voice":            voice,
            }

        # ── known face — check liveness ───────────────────────────────────────
        liveness_ok = (
            tracker["liveness_passed"]
            and tracker["liveness_name"] == name
        )
        return {
            "name":             name,
            "action":           "AUTHORIZED" if liveness_ok else "WAIT_LIVENESS",
            "risk":             "Safe",
            "confidence":       round(confidence, 2),
            "centroid_distance": round(centroid_dist, 3),
            "liveness":         "PASSED" if liveness_ok else "BLINK_REQUIRED",
            "blink_count":      tracker["blink_count"],
            "unknown_count":    unknown_count,
            "location":         _box_to_location(tracker["box"]),
            "voice":            (
                f"Welcome, {name}."
                if liveness_ok
                else "Please blink to verify live person."
            ),
        }

    # ── public entry point ────────────────────────────────────────────────────

    def process_frame(self, rgb_frame) -> list[dict]:
        """
        Process one (small, RGB) frame.  Returns a list of result dicts,
        one per tracked face.  Compatible with the interface main.py expects.
        """
        if not self.model_loaded:
            logger.debug("Model not loaded — skipping frame.")
            return []

        now = time.monotonic()

        # detect faces
        locations = face_recognition.face_locations(
            rgb_frame, number_of_times_to_upsample=0, model="hog"
        )
        boxes = [_location_to_box(loc) for loc in locations]

        # assign to persistent trackers
        assignments = self._assign_trackers(boxes, now)

        # embed + vote
        for tid, location in zip(assignments, locations):
            encodings = face_recognition.face_encodings(
                rgb_frame,
                known_face_locations=[location],
                num_jitters=1,
                model="small",
            )
            if encodings:
                pred = predict_embedding(encodings[0], self._model_bundle)
            else:
                pred = {"name": "Unknown", "confidence": 0.0, "centroid_distance": float("inf")}

            t = self._trackers[tid]
            t["votes"].append(pred["name"])
            t["model_confidences"].append(pred["confidence"])
            t["centroid_distances"].append(pred["centroid_distance"])

        # liveness — only for stably-identified known faces not yet passed
        liveness_targets = []
        for tid in assignments:
            t = self._trackers[tid]
            stable_name, _, stable = self._voted_identity(t)
            if not stable or stable_name == "Unknown":
                continue
            if t["liveness_name"] != stable_name:
                t["liveness_name"]   = stable_name
                t["liveness_passed"] = False
                t["closed_frames"]   = 0
                t["blink_count"]     = 0
            if not t["liveness_passed"]:
                liveness_targets.append((tid, _box_to_location(t["box"])))

        if liveness_targets:
            landmark_results = face_recognition.face_landmarks(
                rgb_frame,
                [item[1] for item in liveness_targets],
                model="large",
            )
            for (tid, _), landmarks in zip(liveness_targets, landmark_results):
                self._update_blink(self._trackers[tid], landmarks)

        # unknown risk
        stable_unknown_present = any(
            stable and voted_name == "Unknown"
            for voted_name, _, stable in (
                self._voted_identity(self._trackers[tid])
                for tid in assignments
            )
        )
        unknown_count, unknown_risk = self._update_unknown_event(
            stable_unknown_present, now
        )

        # build results
        results = []
        for tid in assignments:
            result = self._build_result(
                self._trackers[tid], unknown_count, unknown_risk
            )
            logger.info(
                "%s | %s | %s | liveness=%s",
                result["name"], result["action"],
                result["risk"], result["liveness"],
            )
            results.append(result)

        return results