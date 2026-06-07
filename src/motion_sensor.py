import time
import logging

logger = logging.getLogger(__name__)

# Try importing RPi.GPIO — falls back to mock mode if not on RPi
try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except (ImportError, RuntimeError):
    RPI_AVAILABLE = False
    logger.warning("RPi.GPIO not available. Running in MOCK mode (motion always detected).")


class MotionSensor:

    def __init__(self, pin: int):
        self.pin = pin
        self.mock_mode = not RPI_AVAILABLE

        if not self.mock_mode:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.IN)
            logger.info(f"Motion sensor initialized on GPIO pin {self.pin}")
        else:
            logger.info("Motion sensor running in MOCK mode.")

    def is_motion_detected(self) -> bool:
        if self.mock_mode:
            # In mock mode, always return True so the app runs on non-RPi machines
            return True

        return GPIO.input(self.pin) == GPIO.HIGH

    def wait_for_motion(self, poll_interval: float = 0.1):
        logger.info("Waiting for motion...")
        while not self.is_motion_detected():
            time.sleep(poll_interval)
        logger.info("Motion detected!")

    def cleanup(self):
        if not self.mock_mode:
            GPIO.cleanup()
            logger.info("GPIO cleaned up.")
