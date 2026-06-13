from gpiozero import MotionSensor
import subprocess
import time

PIR_PIN = 4

pir = MotionSensor(PIR_PIN)

def speak(text):
    """Speak text via espeak to AUX port."""
    try:
        subprocess.run(
            ["espeak", "-v", "en", "-s", "150", text],
            check=True
        )
    except FileNotFoundError:
        print(f"[SPEAKER] {text}")
    except subprocess.CalledProcessError as e:
        print(f"espeak error: {e}")

print(f"PIR test on GPIO {PIR_PIN}")
print("Waiting for motion...\n")

try:
    while True:
        pir.wait_for_motion()
        print(f"Motion detected!")
        speak("Motion detected. Scanning.")

        pir.wait_for_no_motion()
        print("Motion stopped.")

except KeyboardInterrupt:
    print("\nTest stopped.")