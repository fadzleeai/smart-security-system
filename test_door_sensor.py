#!/usr/bin/env python3
"""
MC38 Door/Window Magnetic Sensor Test
--------------------------------------
Wiring:
  - One wire  → GPIO 6
  - Other wire → GND

The MC38 is a normally-closed (NC) reed switch.
With internal pull-up enabled on GPIO 6:
  - Door CLOSED  → magnet holds switch CLOSED → pin reads LOW  (0)
  - Door OPEN    → magnet removed, switch OPEN → pin reads HIGH (1)
"""

import RPi.GPIO as GPIO
import time

# ── Configuration ──────────────────────────────────────────────
SENSOR_PIN = 6          # GPIO BCM pin number
POLL_INTERVAL = 0.1     # seconds between reads
# ───────────────────────────────────────────────────────────────


def setup():
    GPIO.setmode(GPIO.BCM)
    # Pull-up: when door is closed (switch closed to GND), pin reads LOW
    GPIO.setup(SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    print(f"[INFO] MC38 sensor initialised on GPIO {SENSOR_PIN} (BCM)")
    print("[INFO] Internal pull-up resistor ENABLED")
    print("-" * 45)


def read_door_state() -> str:
    """Return 'CLOSED' or 'OPEN' based on pin level."""
    level = GPIO.input(SENSOR_PIN)
    # LOW  (0) → switch conducting → door CLOSED
    # HIGH (1) → switch open      → door OPEN
    return "CLOSED" if level == GPIO.LOW else "OPEN"


def run_poll_loop():
    """Continuously poll the sensor and print state changes."""
    last_state = None
    print("[INFO] Monitoring door sensor … Press Ctrl+C to stop.\n")

    try:
        while True:
            state = read_door_state()
            if state != last_state:
                timestamp = time.strftime("%H:%M:%S")
                icon = "🔒" if state == "CLOSED" else "🔓"
                print(f"[{timestamp}]  Door {icon}  {state}")
                last_state = state
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n[INFO] Test stopped by user.")


def run_single_read():
    """Read and print the current door state once."""
    state = read_door_state()
    raw   = GPIO.input(SENSOR_PIN)
    print(f"  GPIO {SENSOR_PIN} raw level : {raw}  ({'LOW' if raw == 0 else 'HIGH'})")
    print(f"  Door state        : {state}")


def main():
    setup()

    print("Select test mode:")
    print("  1 – Single read")
    print("  2 – Continuous polling (default)")
    try:
        choice = input("Enter 1 or 2 [2]: ").strip() or "2"
    except EOFError:
        choice = "2"

    if choice == "1":
        run_single_read()
    else:
        run_poll_loop()

    GPIO.cleanup()
    print("[INFO] GPIO cleaned up. Goodbye.")


if __name__ == "__main__":
    main()