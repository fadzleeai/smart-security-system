import RPi.GPIO as GPIO
import time

PIR_PIN = 17

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
# ADDED: pull_up_down=GPIO.PUD_DOWN prevents the pin from floating
GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

print("Initializing PIR sensor... (Please wait 30 seconds)")
time.sleep(30) # INCREASED: Gives the sensor time to calibrate to the room
print("PIR Ready.")
print("Move in front of the sensor.")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        if GPIO.input(PIR_PIN):
            # Pad with spaces to overwrite any leftover \r text
            print(f"[{time.strftime('%H:%M:%S')}] MOTION DETECTED!          ")
            
            while GPIO.input(PIR_PIN):
                time.sleep(0.2)
        else:
            # Pad with spaces to ensure clean overwriting
            print(f"[{time.strftime('%H:%M:%S')}] No motion...              ", end="\r")
        
        time.sleep(0.2)

except KeyboardInterrupt:
    print("\nTest stopped.")

finally:
    GPIO.cleanup()
    print("GPIO cleaned up.")