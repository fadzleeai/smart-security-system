import logging
import subprocess
import os

logger = logging.getLogger(__name__)


class Speaker:

    AUDIO_DEVICE = "plughw:2,0"  # bcm2835 Headphones (3.5mm jack)

    def __init__(self, language: str = "en", speed: int = 150):
        self.language = language
        self.speed = speed
        self.mode = None

        espeak_cmd = "where" if os.name == "nt" else "which"
        espeak_found = subprocess.run([espeak_cmd, "espeak-ng"], capture_output=True).returncode == 0
        aplay_found = subprocess.run([espeak_cmd, "aplay"], capture_output=True).returncode == 0

        if espeak_found and aplay_found:
            self.mode = "espeak-ng"
            logger.info(f"Speaker initialized with espeak-ng + aplay pipeline (device: {self.AUDIO_DEVICE}).")
        else:
            self.mode = "mock"
            logger.warning("espeak-ng or aplay not found. Speaker running in MOCK mode (print only).")

    def say(self, text: str):
        logger.info(f"TTS: {text}")

        if self.mode == "espeak-ng":
            try:
                espeak = subprocess.Popen(
                    ["espeak-ng", "-a", "200", "-v", self.language, "-s", str(self.speed), text, "--stdout"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL  # added to suppress espeak-ng terminal noise
                )
                subprocess.run(
                    ["aplay", "-D", self.AUDIO_DEVICE],  # pinned to 3.5mm jack
                    stdin=espeak.stdout,
                    stderr=subprocess.DEVNULL,
                    check=True
                )
                espeak.wait()
            except Exception as e:
                logger.error(f"espeak-ng say failed: {e}")

        else:
            print(f"[SPEAKER] {text}")

    def cleanup(self):
        pass