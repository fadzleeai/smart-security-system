# Smart Security System

AI-powered face recognition security system for Raspberry Pi 4.

**Hardware:** RPi 4 + USB/CSI camera + PIR motion sensor + speaker

---

## How It Works

1. PIR motion sensor detects movement
2. Camera activates and scans for faces
3. Known face → TTS: *"Welcome, {name}"*
4. Unknown face → TTS: *"Access denied"* → escalates to *"Security alert"* after repeated detections
5. Camera sleeps after no activity

---

## Project Structure

```
Smart_Security/
├── main.py                      # Entry point
├── admin.py                     # Admin CLI
├── config.json                  # All settings (edit without rebuild)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml           # Base config (Windows/Mac dev)
├── docker-compose.rpi.yml       # RPi overrides (camera + GPIO)
├── known_faces/                 # Face images (gitignored, persists as volume)
├── logs/                        # Log files (gitignored, persists as volume)
└── src/
    ├── face_recognition_engine.py
    ├── motion_sensor.py
    ├── speaker.py
    └── register_face.py
```

---

## Hardware Wiring

| Component  | RPi Pin       |
|------------|---------------|
| PIR Signal | GPIO 17 (BCM) |
| PIR VCC    | 5V            |
| PIR GND    | GND           |
| Camera     | USB or CSI    |
| Speaker    | 3.5mm audio   |

> GPIO pin can be changed via admin panel or `config.json`.

---

## Quick Start (on RPi)

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/Smart_Security.git
cd Smart_Security
```

### 2. Enable camera on RPi (first time only)

```bash
sudo raspi-config
# Interface Options → Camera → Enable
```

### 3. Register faces

```bash
docker compose -f docker-compose.yml -f docker-compose.rpi.yml run register
```

### 4. Start the security system

```bash
docker compose -f docker-compose.yml -f docker-compose.rpi.yml up security
```

> Add `-d` to run in background:
> ```bash
> docker compose -f docker-compose.yml -f docker-compose.rpi.yml up -d security
> ```

### 5. Admin panel

```bash
docker compose -f docker-compose.yml -f docker-compose.rpi.yml run admin
```

---

## Development (Windows/Mac, no hardware)

The system runs in mock mode on non-RPi machines:
- **Motion sensor** → always returns motion detected
- **GPIO** → skipped gracefully
- **Speaker** → prints TTS text to console if no audio engine found

**Run directly (no Docker):**
```bash
python main.py
```

**Run via Docker (no camera/GPIO needed):**
```bash
docker compose run admin
docker compose up security
```

---

## Admin Panel Options

```
 1. System info (neofetch)
 ─────────────────────────
 2. View all settings
 3. Change tolerance
 4. Change GPIO pin
 5. Change TTS speed
 6. Change sleep timeout
 ─────────────────────────
 7. List registered faces
 8. Register new face
 9. Delete a face
 ─────────────────────────
10. View logs
11. Clear logs
 ─────────────────────────
 0. Exit
```

---

## Config Reference (`config.json`)

| Key                             | Default | Description                            |
|---------------------------------|---------|----------------------------------------|
| `tolerance`                     | 0.5     | Face match threshold (0.0–1.0)         |
| `gpio_pin`                      | 17      | PIR sensor GPIO pin (BCM)              |
| `camera_index`                  | 0       | Camera device index                    |
| `frame_skip`                    | 2       | Process every Nth frame (performance)  |
| `camera_warmup_seconds`         | 2       | Seconds to wait after motion detected  |
| `sleep_after_detection_seconds` | 5       | Seconds of inactivity before sleep     |
| `tts_language`                  | en      | TTS language code                      |
| `tts_speed`                     | 150     | TTS speed (words per minute)           |
| `unknown_risk_medium_threshold` | 3       | Unknown detections before Medium risk  |
| `unknown_risk_high_threshold`   | 5       | Unknown detections before HIGH alert   |

> Config changes take effect on next restart. No rebuild needed.

---

## Rebuild After Code Changes

```bash
docker compose build
docker compose -f docker-compose.yml -f docker-compose.rpi.yml up security
```