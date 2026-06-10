from gpiozero import MotionSensor
import pyttsx3

PIR_PIN = 4

pir = MotionSensor(PIR_PIN)

engine = pyttsx3.init()
engine.setProperty('rate', 150)

def speak(text):
    try:
        engine.say(text)
        engine.runAndWait()
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