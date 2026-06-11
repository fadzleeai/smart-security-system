import logging
import subprocess
import os

logger = logging.getLogger(__name__)


class Speaker:

    def __init__(self, language: str = "en", speed: int = 150):
        self.language = language
        self.speed = speed
        self.mode = None

        # Check for espeak-ng with aplay pipeline (matches test_pir_speaker.py)
        espeak_cmd = "where" if os.name == "nt" else "which"
        espeak_found = subprocess.run([espeak_cmd, "espeak-ng"], capture_output=True).returncode == 0
        aplay_found = subprocess.run([espeak_cmd, "aplay"], capture_output=True).returncode == 0

        if espeak_found and aplay_found:
            self.mode = "espeak-ng"
            logger.info("Speaker initialized with espeak-ng + aplay pipeline.")
        else:
            self.mode = "mock"
            logger.warning("espeak-ng or aplay not found. Speaker running in MOCK mode (print only).")

    def say(self, text: str):
        logger.info(f"TTS: {text}")

        if self.mode == "espeak-ng":
            try:
                # Same pipeline as test_pir_speaker.py
                espeak = subprocess.Popen(
                    ["espeak-ng", "-a", "200", "-v", self.language, "-s", str(self.speed), text, "--stdout"],
                    stdout=subprocess.PIPE
                )
                subprocess.run(
                    ["aplay"],
                    stdin=espeak.stdout,
                    stderr=subprocess.DEVNULL,
                    check=True
                )
                espeak.wait()
            except Exception as e:
                logger.error(f"espeak-ng say failed: {e}")

        else:
            # Mock mode — just print
            print(f"[SPEAKER] {text}")

    def cleanup(self):
        # No persistent engine to clean up
        pass