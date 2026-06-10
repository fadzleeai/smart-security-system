from gpiozero import MotionSensor
import subprocess
import time
from signal import pause

PIR_PIN = 4
pir = MotionSensor(PIR_PIN)

def speak(text):
    try:
        espeak = subprocess.Popen(
            ["espeak-ng", "-a", "200", text, "--stdout"],
            stdout=subprocess.PIPE
        )
        # Added stderr=subprocess.DEVNULL to hide aplay's default terminal text
        subprocess.run(
            ["aplay"], 
            stdin=espeak.stdout, 
            stderr=subprocess.DEVNULL, 
            check=True
        )
        espeak.wait()
    except Exception as e:
        print(f"[SPEAKER ERROR] {e}")

def on_motion():
    # Added timestamps to the terminal output
    print(f"[{time.strftime('%H:%M:%S')}] Motion detected!")
    speak("Motion detected. Scanning.")

def on_no_motion():
    print(f"[{time.strftime('%H:%M:%S')}] Motion stopped.")
    # Optional: speak("Area clear.")

print(f"Initializing PIR on GPIO {PIR_PIN}...")
# Wait for the sensor to settle into a "no motion" state before arming
pir.wait_for_no_motion() 
print("Ready. Waiting for motion...\n")

# Link the sensor events to our custom functions
pir.when_motion = on_motion
pir.when_no_motion = on_no_motion

try:
    # pause() keeps the script alive and listening for events in the background
    pause()
except KeyboardInterrupt:
    print("\nTest stopped cleanly.")