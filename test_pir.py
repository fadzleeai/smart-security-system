import RPi.GPIO as GPIO
import time

PIR_PIN = 17

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

print("Initializing PIR sensor...")
time.sleep(5)
print("PIR Ready.")
print("Move in front of the sensor.")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        if GPIO.input(PIR_PIN):
            print(f"[{time.strftime('%H:%M:%S')}] MOTION DETECTED!")
            while GPIO.input(PIR_PIN):
                time.sleep(0.2)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] No motion...", end="\r")
        time.sleep(0.2)

except KeyboardInterrupt:
    print("\nTest stopped.")

finally:
    GPIO.cleanup()
    print("GPIO cleaned up.")