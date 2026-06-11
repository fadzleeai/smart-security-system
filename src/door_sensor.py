import time
import logging

logger = logging.getLogger(__name__)

# Try importing gpiozero — falls back to mock mode if not on RPi
try:
    from gpiozero import Button
    GPIOZERO_AVAILABLE = True
except (ImportError, RuntimeError):
    GPIOZERO_AVAILABLE = False
    logger.warning("gpiozero not available. Door sensor running in MOCK mode (door always closed).")


class DoorSensor:
    """
    MC38 Magnetic Door/Window Sensor
    ---------------------------------
    Wiring:
      - One wire  → GPIO pin (default 6)
      - Other wire → GND

    NC (normally-closed) reed switch with internal pull-up:
      - Door CLOSED → magnet holds switch closed → pin LOW
      - Door OPEN   → magnet removed, switch open → pin HIGH

    Logic:
      - Door OPEN  + UNAUTHORIZED → alarm triggered, stranger saved
      - Door OPEN  + AUTHORIZED   → access logged, no alarm
      - Door CLOSED               → no action
    """

    def __init__(self, pin: int = 6):
        self.pin = pin
        self.mock_mode = not GPIOZERO_AVAILABLE

        if not self.mock_mode:
            # pull_up=True matches test_door_sensor.py PUD_UP behavior
            self._sensor = Button(pin, pull_up=True)
            logger.info(f"Door sensor initialized on GPIO pin {self.pin}")
        else:
            logger.info("Door sensor running in MOCK mode (door always closed).")

    def is_open(self) -> bool:
        """Returns True if door is open, False if closed."""
        if self.mock_mode:
            return False
        # Button.is_pressed = pin LOW = door CLOSED, so invert
        return not self._sensor.is_pressed

    def is_closed(self) -> bool:
        return not self.is_open()

    def handle_door_event(self, authorized: bool, name: str, speaker, save_stranger_fn=None, frame=None, risk: str = "HIGH"):
        """
        Call this when a face is recognized and door state needs to be evaluated.

        Args:
            authorized:      True if face is known/authorized
            name:            Name of the person (or 'Unknown')
            speaker:         Speaker instance for TTS alerts
            save_stranger_fn: Callback to save stranger image (optional)
            frame:           Current camera frame for saving stranger image
            risk:            Risk level string passed to save_stranger_fn
        """
        if not self.is_open():
            return  # Door closed, nothing to act on

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        if authorized:
            # Authorized person opened door — log it, no alarm
            logger.info(f"[DOOR] AUTHORIZED entry — {name} at {timestamp}")
            speaker.say(f"Welcome, {name}.")

        else:
            # Unauthorized person — door opened, raise alarm
            logger.warning(f"[DOOR] UNAUTHORIZED entry attempt — {name} at {timestamp} — ALARM TRIGGERED")
            speaker.say("Unauthorized access detected. Alarm triggered.")

            # Save stranger image if callback provided
            if save_stranger_fn and frame is not None:
                save_stranger_fn(frame, risk, logger)

    def cleanup(self):
        if not self.mock_mode:
            self._sensor.close()
            logger.info("Door sensor closed.")