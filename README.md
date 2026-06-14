# Smart Security System

AI-powered face recognition security system for Raspberry Pi.

**Hardware:** RPi 4/5 + USB/CSI camera + PIR motion sensor + MC38 door sensor + speaker

---

## How It Works

1. PIR motion sensor detects movement
2. Camera activates and scans for faces
3. Known face → TTS: *"Welcome, {name}"*
4. Unknown face → TTS: *"Access denied"* → escalates to *"Security alert"* after repeated detections
5. Door sensor monitors entry:
   - Door opened by authorized person → entry logged
   - Door opened by unauthorized person → alarm triggered, stranger image saved
6. Stranger images saved locally with timestamp and risk level
7. Camera sleeps after no face detected for X seconds
8. Web dashboard available for live monitoring and face registration

---

## Project Structure

```
smart-security-system/
├── main.py                      # Entry point
├── config.json                  # All settings (edit without rebuild)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml           # Base compose config
├── docker-compose.rpi.yml       # RPi overrides (camera + GPIO devices)
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
    ├── door_sensor.py
    ├── speaker.py
    ├── admin.py
    └── webapp.py
```

---

## Hardware Wiring

| Component       | RPi Pin        |
|-----------------|----------------|
| PIR Signal      | GPIO 17 (BCM)  |
| PIR VCC         | 5V             |
| PIR GND         | GND            |
| Door Sensor     | GPIO 6 (BCM)   |
| Door Sensor GND | GND            |
| Camera          | USB or CSI     |
| Speaker         | 3.5mm audio    |

> GPIO pins can be changed via admin panel or `config.json`.

---

## Quick Start (on RPi)

### 1. Clone the repo

```bash
git clone https://github.com/fadzleeai/smart-security-system.git
cd smart-security-system
```

### 2. Install Docker (first time only)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

### 3. Transfer the pre-built image from your laptop

```bash
# On laptop
docker save smart_security -o smart_security.tar
scp smart_security.tar admin@<pi-ip>:~/

# On Pi
docker load < smart_security.tar
```

> Or copy via USB drive for faster transfer.

### 4. Run startup script

```bash
bash start.sh
```

### 5. Access web dashboard

Open from any device on the same network:
```
https://<rpi-ip>:5000
```
> Browser will warn about self-signed certificate — click **Advanced → Proceed anyway**.

Password: `admin123` (change in `config.json` → `web_password`)

### 6. Admin panel (local only, via SSH)

```bash
bash admin.sh
```

### 7. Stop everything

```bash
bash stop.sh
```

---

## Web Dashboard

| Page | URL | Description |
|------|-----|-------------|
| Login | `/login` | Password protected |
| Dashboard | `/` | Live camera feed, activity log, stranger captures |
| Register | `/register` | Register faces via laptop webcam or RPi camera stream |

---

## Admin Panel Options

```
 1. System info (neofetch)
 ─────────────────────────
 2. View all settings
 3. Change tolerance
 4. Change GPIO pin (PIR sensor)
 5. Change door sensor GPIO pin
 6. Change TTS speed
 7. Change sleep timeout
 ─────────────────────────
 8. List registered faces
 9. Register new face
10. Delete a face
 ─────────────────────────
11. View logs
12. Clear logs
 ─────────────────────────
 0. Exit
```

---

## Development (Windows/Mac, no hardware)

The system runs in mock mode on non-RPi machines:
- **Motion sensor** → always returns motion detected
- **GPIO** → skipped gracefully
- **Camera** → warning logged, system continues without face recognition
- **Speaker** → prints TTS text to console

**Run directly (no Docker):**
```bash
python main.py
python src/webapp.py   # web dashboard at https://localhost:5000
```

---

## Rebuilding After Code Changes

Build on laptop and transfer to Pi:
```bash
# Laptop
docker buildx build --platform linux/arm64 -t smart_security . --load
docker save smart_security -o smart_security.tar
scp smart_security.tar admin@<pi-ip>:~/

# Pi
docker load < smart_security.tar
bash stop.sh && bash start.sh
```

> Rebuilds are fast for code-only changes — Docker caches all system deps and dlib.

---

## Config Reference (`config.json`)

| Key | Default | Description |
|-----|---------|-------------|
| `tolerance` | 0.5 | Face match threshold (0.0–1.0, lower = stricter) |
| `gpio_pin` | 17 | PIR sensor GPIO pin (BCM) |
| `door_sensor_pin` | 6 | Door sensor GPIO pin (BCM) |
| `camera_index` | 0 | Camera device index |
| `frame_skip` | 2 | Process every Nth frame (performance) |
| `camera_warmup_seconds` | 2 | Seconds to wait after motion detected |
| `sleep_after_detection_seconds` | 5 | Seconds of no face before re-arm |
| `tts_language` | en | TTS language code |
| `tts_speed` | 150 | TTS speed (words per minute) |
| `unknown_risk_medium_threshold` | 3 | Unknown detections before Medium risk |
| `unknown_risk_high_threshold` | 5 | Unknown detections before HIGH alert |
| `web_password` | admin123 | Web dashboard password |
| `web_port` | 5000 | Web dashboard port |
| `stream_port` | 8080 | Internal camera stream port |

> Config changes take effect on next restart. No rebuild needed.