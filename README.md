# Smart Security System

AI-powered face recognition security system for Raspberry Pi 4.

**Hardware:** RPi 4 + USB/CSI camera + PIR motion sensor + speaker

---

## How It Works

1. PIR motion sensor detects movement
2. Camera activates and scans for faces
3. Known face → TTS: *"Welcome, {name}"*
4. Unknown face → TTS: *"Access denied"* → escalates to *"Security alert"* after repeated detections
5. Stranger images saved locally with timestamp and risk level
6. Camera sleeps after no activity
7. Web dashboard available for live monitoring and face registration

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
├── start.sh                     # Start everything on RPi
├── stop.sh                      # Stop everything
├── admin.sh                     # Open admin CLI
├── known_faces/                 # Face images (gitignored, persists as volume)
├── strangers/                   # Stranger captures (gitignored, persists as volume)
├── logs/                        # Log files (gitignored, persists as volume)
├── templates/
│   ├── login.html
│   ├── dashboard.html
│   └── register.html
└── src/
    ├── face_recognition_engine.py
    ├── motion_sensor.py
    ├── speaker.py
    ├── register_face.py
    └── webapp.py
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
git clone https://github.com/fadzleeai/smart-security-system.git
cd smart-security-system
```

### 2. Enable camera on RPi (first time only)

```bash
sudo raspi-config
# Interface Options → Camera → Enable
```

### 3. Run startup script

```bash
bash start.sh
```

That's it. The script will:
- Check Docker is installed
- Prompt to register faces if none exist
- Build the Docker image if needed (first time is slow — dlib compiles from source)
- Start the security system and web dashboard
- Print your web dashboard URL

### 4. Access web dashboard

Open from any device on the same WiFi:
```
http://<rpi-ip>:5000
```
Password: `admin123` (change in `config.json` → `web_password`)

### 5. Admin panel (via SSH)

```bash
bash admin.sh
```

### 6. Stop everything

```bash
bash stop.sh
```

---

## Web Dashboard

| Page | URL | Description |
|------|-----|-------------|
| Login | `/login` | Password protected |
| Dashboard | `/` | Live camera feed, activity log, stranger captures |
| Register | `/register` | Register faces via webcam or RPi camera |

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

## Development (Windows/Mac, no hardware)

The system runs in mock mode on non-RPi machines:
- **Motion sensor** → always returns motion detected
- **GPIO** → skipped gracefully
- **Speaker** → prints TTS text to console if no audio engine found

**Run directly (no Docker):**
```bash
python main.py
python src/webapp.py   # web dashboard at http://localhost:5000
```

**Run via Docker:**
```bash
docker compose up security
docker compose up web
docker compose run admin
```

---

## Config Reference (`config.json`)

| Key                             | Default   | Description                            |
|---------------------------------|-----------|----------------------------------------|
| `tolerance`                     | 0.5       | Face match threshold (0.0–1.0)         |
| `gpio_pin`                      | 17        | PIR sensor GPIO pin (BCM)              |
| `camera_index`                  | 0         | Camera device index                    |
| `frame_skip`                    | 2         | Process every Nth frame (performance)  |
| `camera_warmup_seconds`         | 2         | Seconds to wait after motion detected  |
| `sleep_after_detection_seconds` | 5         | Seconds of inactivity before sleep     |
| `tts_language`                  | en        | TTS language code                      |
| `tts_speed`                     | 150       | TTS speed (words per minute)           |
| `unknown_risk_medium_threshold` | 3         | Unknown detections before Medium risk  |
| `unknown_risk_high_threshold`   | 5         | Unknown detections before HIGH alert   |
| `web_password`                  | admin123  | Web dashboard password                 |
| `web_port`                      | 5000      | Web dashboard port                     |

> Config changes take effect on next restart. No rebuild needed.

---

## Rebuild After Code Changes

```bash
docker compose build
bash start.sh
```