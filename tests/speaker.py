import subprocess

def speak(text):
    print(f"Speaking: {text}")
    # We use 2>/dev/null to hide the ugly 'Playing WAVE' terminal text from aplay
    command = f'espeak-ng -a 200 "{text}" --stdout | aplay 2>/dev/null'
    subprocess.run(command, shell=True)

# Test it out
speak("Hello! I am now speaking directly from Python.")
speak("This method is much more stable on a Raspberry Pi.")