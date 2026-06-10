import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("RPi.GPIO not found. Are you on a Raspberry Pi?")
    exit(1)

# =========================================
# CONFIG
# =========================================

PIR_PIN = 17

# =========================================
# SETUP
# =========================================

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

print(f"PIR sensor test — GPIO pin {PIR_PIN}")
print("Waiting for sensor to settle (2s)...")
time.sleep(2)
print("Ready. Move in front of the sensor.\n")
print("Press Ctrl+C to stop.\n")

# =========================================
# LOOP
# =========================================

try:
    while True:
        if GPIO.input(PIR_PIN) == GPIO.HIGH:
            print(f"[{time.strftime('%H:%M:%S')}] MOTION DETECTED!")
        else:
            print(f"[{time.strftime('%H:%M:%S')}] No motion...", end="\r")
        time.sleep(0.2)

except KeyboardInterrupt:
    print("\nTest stopped.")

finally:
    GPIO.cleanup()
    print("GPIO cleaned up.")