from gpiozero import MotionSensor
import subprocess
import time
from signal import pause

PIR_PIN = 4
AUDIO_DEVICE = "plughw:2,0"  # bcm2835 Headphones (3.5mm jack)

pir = MotionSensor(PIR_PIN)

def speak(text):
    try:
        espeak = subprocess.Popen(
            ["espeak-ng", "-a", "200", text, "--stdout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["aplay", "-D", AUDIO_DEVICE],
            stdin=espeak.stdout,
            stderr=subprocess.DEVNULL,
            check=True
        )
        espeak.wait()
    except Exception as e:
        print(f"[SPEAKER ERROR] {e}")

def on_motion():
    print(f"[{time.strftime('%H:%M:%S')}] Motion detected!")
    speak("Motion detected. Scanning.")

def on_no_motion():
    print(f"[{time.strftime('%H:%M:%S')}] Motion stopped.")

print(f"Initializing PIR on GPIO {PIR_PIN}...")
pir.wait_for_no_motion()
print("Ready. Waiting for motion...\n")

pir.when_motion = on_motion
pir.when_no_motion = on_no_motion

try:
    pause()
except KeyboardInterrupt:
    print("\nTest stopped cleanly.")