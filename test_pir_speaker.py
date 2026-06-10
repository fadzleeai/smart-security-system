from gpiozero import MotionSensor
import subprocess

PIR_PIN = 4

pir = MotionSensor(PIR_PIN)

def speak(text):
    try:
        espeak = subprocess.Popen(
            ["espeak-ng", "-a", "200", text, "--stdout"],
            stdout=subprocess.PIPE
        )
        subprocess.run(["aplay"], stdin=espeak.stdout, check=True)
        espeak.wait()
    except Exception as e:
        print(f"[SPEAKER] {text} (error: {e})")

print(f"PIR test on GPIO {PIR_PIN}")
print("Waiting for motion...\n")

try:
    while True:
        pir.wait_for_motion()
        print("Motion detected!")
        speak("Motion detected. Scanning.")

        pir.wait_for_no_motion()
        print("Motion stopped.")

except KeyboardInterrupt:
    print("\nTest stopped.")