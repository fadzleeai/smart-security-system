import time
import logging

logger = logging.getLogger(__name__)

# Try importing gpiozero — falls back to mock mode if not on RPi
try:
    from gpiozero import MotionSensor as _GpioMotionSensor
    GPIOZERO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIOZERO_AVAILABLE = False
    logger.warning("gpiozero not available. Running in MOCK mode (motion always detected).")


class MotionSensor:

    def __init__(self, pin: int):
        self.pin = pin
        self.mock_mode = not GPIOZERO_AVAILABLE

        if not self.mock_mode:
            self._sensor = _GpioMotionSensor(pin)
            # Wait for sensor to settle before arming (same as test file)
            logger.info(f"Motion sensor initializing on GPIO pin {self.pin}, waiting to settle...")
            self._sensor.wait_for_no_motion()
            logger.info(f"Motion sensor ready on GPIO pin {self.pin}")
        else:
            logger.info("Motion sensor running in MOCK mode.")

    def is_motion_detected(self) -> bool:
        if self.mock_mode:
            return True
        return self._sensor.motion_detected

    def wait_for_motion(self, poll_interval: float = 0.1):
        logger.info("Waiting for motion...")
        if self.mock_mode:
            return
        self._sensor.wait_for_motion()
        logger.info("Motion detected!")

    def cleanup(self):
        if not self.mock_mode:
            self._sensor.close()
            logger.info("Motion sensor closed.")