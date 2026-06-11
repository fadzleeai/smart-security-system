import json
import os
import sys
import subprocess

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
KNOWN_FACES_DIR = os.environ.get("KNOWN_FACES_DIR", "known_faces")

# =========================================
# COLORS
# =========================================

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

# =========================================
# CLEAR SCREEN (cross-platform)
# =========================================

def clear():    
    os.system("cls" if os.name == "nt" else "clear")

# =========================================
# LOGO
# =========================================

def print_logo():
    try:
        with open("logo.txt", "r") as f:
            print(GREEN + f.read() + RESET)
    except FileNotFoundError:
        print(GREEN + "Smart Security" + RESET)

# =========================================
# CONFIG HELPERS
# =========================================

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(config: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)
    print("Config saved.")

# =========================================
# MENU HELPERS
# =========================================

def header():
    clear()
    print_logo()
    print(YELLOW + "=" * 40)
    print("   Smart Security — Admin Panel")
    print("=" * 40 + RESET)

def pause():
    input("\nPress Enter to continue...")

# =========================================
# MENU ACTIONS
# =========================================

def show_neofetch():
    cmd = "winfetch" if os.name == "nt" else "neofetch"
    try:
        result = subprocess.run([cmd], capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"'{cmd}' ran but returned an error.")
    except FileNotFoundError:
        if os.name == "nt":
            print("winfetch not installed.")
            print("Install it with: winget install winfetch")
        else:
            print("neofetch not installed.")
            print("Install it with: sudo apt install neofetch")
    pause()

def view_settings(config: dict):
    print("\n--- Current Settings ---")
    for key, value in config.items():
        print(f"  {key}: {value}")

def change_tolerance(config: dict):
    print(f"\nCurrent tolerance: {config['tolerance']} (lower = stricter, range 0.0 - 1.0)")
    try:
        val = float(input("New tolerance: ").strip())
        if 0.0 <= val <= 1.0:
            config["tolerance"] = val
            save_config(config)
        else:
            print("Value must be between 0.0 and 1.0.")
    except ValueError:
        print("Invalid input.")

def change_gpio_pin(config: dict):
    print(f"\nCurrent GPIO pin: {config['gpio_pin']}")
    try:
        val = int(input("New GPIO pin (BCM numbering): ").strip())
        config["gpio_pin"] = val
        save_config(config)
    except ValueError:
        print("Invalid input.")

def change_door_sensor_pin(config: dict):
    print(f"\nCurrent door sensor GPIO pin: {config.get('door_sensor_pin', 'Not set')} (BCM numbering)")
    try:
        val = int(input("New door sensor GPIO pin: ").strip())
        config["door_sensor_pin"] = val
        save_config(config)
    except ValueError:
        print("Invalid input.")

def change_tts_speed(config: dict):
    print(f"\nCurrent TTS speed: {config['tts_speed']} words/min (default 150)")
    try:
        val = int(input("New speed: ").strip())
        config["tts_speed"] = val
        save_config(config)
    except ValueError:
        print("Invalid input.")

def change_sleep_timeout(config: dict):
    print(f"\nCurrent sleep timeout: {config['sleep_after_detection_seconds']}s")
    try:
        val = int(input("New timeout (seconds): ").strip())
        config["sleep_after_detection_seconds"] = val
        save_config(config)
    except ValueError:
        print("Invalid input.")

def list_faces():
    print("\n--- Registered Faces ---")
    if not os.path.exists(KNOWN_FACES_DIR):
        print("  No known_faces folder found.")
        return

    files = [f for f in os.listdir(KNOWN_FACES_DIR)
             if f.lower().endswith((".jpg", ".png"))]

    if not files:
        print("  No faces registered yet.")
    else:
        for i, f in enumerate(files, 1):
            name = os.path.splitext(f)[0]
            print(f"  {i}. {name}")

def delete_face():
    if not os.path.exists(KNOWN_FACES_DIR):
        print("No known_faces folder found.")
        return

    files = [f for f in os.listdir(KNOWN_FACES_DIR)
             if f.lower().endswith((".jpg", ".png"))]

    if not files:
        print("No faces registered.")
        return

    print("\n--- Delete a Face ---")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {os.path.splitext(f)[0]}")

    try:
        choice = int(input("Enter number to delete (0 to cancel): ").strip())
        if choice == 0:
            return
        if 1 <= choice <= len(files):
            target = os.path.join(KNOWN_FACES_DIR, files[choice - 1])
            confirm = input(f"Delete '{os.path.splitext(files[choice-1])[0]}'? (y/n): ").strip().lower()
            if confirm == "y":
                os.remove(target)
                print("Face deleted.")
            else:
                print("Cancelled.")
        else:
            print("Invalid choice.")
    except ValueError:
        print("Invalid input.")

def register_face():
    print("\nLaunching face registration...")
    subprocess.run([sys.executable, "src/register_face.py"])

def view_logs(config: dict):
    log_file = config.get("log_file", "logs/security.log")
    if not os.path.exists(log_file):
        print(f"No log file found at {log_file}")
        return

    print(f"\n--- Last 30 lines of {log_file} ---")
    with open(log_file, "r") as f:
        lines = f.readlines()
        for line in lines[-30:]:
            print(line, end="")

def clear_logs(config: dict):
    log_file = config.get("log_file", "logs/security.log")
    confirm = input(f"Clear {log_file}? (y/n): ").strip().lower()
    if confirm == "y":
        open(log_file, "w").close()
        print("Logs cleared.")

# =========================================
# MAIN MENU
# =========================================

def main():
    while True:
        config = load_config()
        header()

        face_count = len([
            f for f in os.listdir(KNOWN_FACES_DIR)
            if f.lower().endswith((".jpg", ".png"))
        ] if os.path.exists(KNOWN_FACES_DIR) else [])

        print(f"  Tolerance: {config['tolerance']}  |  PIR GPIO: {config['gpio_pin']}  |  Door GPIO: {config.get('door_sensor_pin', 'N/A')}  |  Faces: {face_count}")
        print()
        print("  1. System info (neofetch)")
        print("  ─────────────────────")
        print("  2. View all settings")
        print("  3. Change tolerance")
        print("  4. Change GPIO pin (PIR sensor)")
        print("  5. Change door sensor GPIO pin")
        print("  6. Change TTS speed")
        print("  7. Change sleep timeout")
        print("  ─────────────────────")
        print("  8. List registered faces")
        print("  9. Register new face")
        print(" 10. Delete a face")
        print("  ─────────────────────")
        print(" 11. View logs")
        print(" 12. Clear logs")
        print("  ─────────────────────")
        print("  0. Exit")
        print()

        choice = input("Choose: ").strip()

        if choice == "1":
            show_neofetch()
        elif choice == "2":
            view_settings(config)
            pause()
        elif choice == "3":
            change_tolerance(config)
            pause()
        elif choice == "4":
            change_gpio_pin(config)
            pause()
        elif choice == "5":
            change_door_sensor_pin(config)
            pause()
        elif choice == "6":
            change_tts_speed(config)
            pause()
        elif choice == "7":
            change_sleep_timeout(config)
            pause()
        elif choice == "8":
            list_faces()
            pause()
        elif choice == "9":
            register_face()
        elif choice == "10":
            delete_face()
            pause()
        elif choice == "11":
            view_logs(config)
            pause()
        elif choice == "12":
            clear_logs(config)
            pause()
        elif choice == "0":
            clear()
            print("Bye.")
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()