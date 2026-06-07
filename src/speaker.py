import logging
import subprocess
import os

logger = logging.getLogger(__name__)

# Try importing pyttsx3 — falls back to espeak subprocess, then mock
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    logger.warning("pyttsx3 not available. Trying espeak fallback.")


class Speaker:

    def __init__(self, language: str = "en", speed: int = 150):
        self.language = language
        self.speed = speed
        self.engine = None
        self.mode = None

        if PYTTSX3_AVAILABLE:
            try:
                self.engine = pyttsx3.init()
                self.engine.setProperty("rate", self.speed)
                self.mode = "pyttsx3"
                logger.info("Speaker initialized with pyttsx3.")
            except Exception as e:
                logger.warning(f"pyttsx3 init failed: {e}. Trying espeak.")

        if self.mode is None:
            # Try espeak as fallback (available on RPi via apt)
            cmd = "where" if os.name == "nt" else "which"
            result = subprocess.run([cmd, "espeak"], capture_output=True)
            if result.returncode == 0:
                self.mode = "espeak"
                logger.info("Speaker initialized with espeak.")
            else:
                self.mode = "mock"
                logger.warning("No TTS engine found. Speaker running in MOCK mode (print only).")

    def say(self, text: str):
        logger.info(f"TTS: {text}")

        if self.mode == "pyttsx3":
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e:
                logger.error(f"pyttsx3 say failed: {e}")

        elif self.mode == "espeak":
            try:
                subprocess.run(
                    ["espeak", "-v", self.language, "-s", str(self.speed), text],
                    check=True
                )
            except subprocess.CalledProcessError as e:
                logger.error(f"espeak failed: {e}")

        else:
            # Mock mode — just print
            print(f"[SPEAKER] {text}")

    def cleanup(self):
        if self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass
