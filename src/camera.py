"""
camera.py — shared camera adapter.

Wraps picamera2 (for CSI Pi Camera modules, v2/v3) with a cv2.VideoCapture
fallback (for USB webcams or non-Pi dev machines), behind a single
cv2.VideoCapture-compatible interface: isOpened() / read() / release().

Why this exists: plain cv2.VideoCapture cannot reliably read frames from
libcamera-backed CSI sensors on current Raspberry Pi OS (Bullseye+/
Bookworm). It may report isOpened()==True but then fail on every .read().
picamera2 is the supported way to grab frames from those sensors.
"""

import time

import cv2

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except (ImportError, RuntimeError):
    PICAMERA2_AVAILABLE = False


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