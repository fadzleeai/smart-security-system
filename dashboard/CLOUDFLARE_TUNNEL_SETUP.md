# Cloudflare Tunnel Setup — Run once on the Raspberry Pi

This gives your Pi a permanent public HTTPS URL (e.g.
`https://yourproject.trycloudflare.com`) WITHOUT port-forwarding, a static
IP, or paying for anything. The tunnel daemon is lightweight — runs
quietly in the background alongside `pi_server.py`.

---

## Step 1 — Install pi_server.py dependencies

```bash
pip install fastapi "uvicorn[standard]"
```

Put `pi_server.py` in the SAME folder as your `security_logs.csv` and
`images/` folder on the Pi (or edit the CSV_PATH / IMAGES_DIR constants
at the top of the file to point at the right location).

Test it works locally first:
```bash
python3 pi_server.py
```
Then from another device on the same WiFi, visit:
```
http://<pi-ip>:8000/health
```
You should see `{"status":"ok"}`. If that works, stop it (Ctrl+C) and move on.

---

## Step 2 — Install cloudflared on the Pi

```bash
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb
```

(If your Pi is 32-bit OS, use `cloudflared-linux-arm.deb` instead of `arm64`.)

Check it installed:
```bash
cloudflared --version
```

---

## Step 3 — Quick test tunnel (no account needed, temporary URL)

This is the fastest way to confirm everything works end-to-end before
setting up a permanent named tunnel:

```bash
cloudflared tunnel --url http://localhost:8000
```

This prints a temporary URL like:
```
https://random-words-1234.trycloudflare.com
```

Visit `<that-url>/health` from your phone (off WiFi, using mobile data) to
confirm it's genuinely reachable from the internet, not just your LAN.

⚠️ This quick-tunnel URL changes every time you restart `cloudflared`. Good
for testing today; for your actual demo/project, do Step 4 once so the URL
never changes.

---

## Step 4 — Permanent named tunnel (do this once, URL never changes)

1. Create a free Cloudflare account at https://dash.cloudflare.com/sign-up
   (you do NOT need to buy a domain — Cloudflare can give you a free
   subdomain workflow via Cloudflare Tunnel's `trycloudflare` alternative,
   OR if you already own/can get a free domain, even easier).

2. Authenticate the Pi:
```bash
cloudflared tunnel login
```
This opens a browser link — log in, authorize.

3. Create a named tunnel:
```bash
cloudflared tunnel create pi-security-project
```
This generates a tunnel ID and a credentials file.

4. Create a config file:
```bash
mkdir -p ~/.cloudflared
nano ~/.cloudflared/config.yml
```
Paste (replace `<TUNNEL-ID>` with the ID from step 3):
```yaml
tunnel: <TUNNEL-ID>
credentials-file: /home/pi/.cloudflared/<TUNNEL-ID>.json

ingress:
  - hostname: pi-security.yourdomain.com   # or your assigned hostname
    service: http://localhost:8000
  - service: http_status:404
```

5. Route DNS (if you have a domain in Cloudflare):
```bash
cloudflared tunnel route dns pi-security-project pi-security.yourdomain.com
```

6. Run it:
```bash
cloudflared tunnel run pi-security-project
```

> **No domain available?** Skip Step 4 and just use the Step 3 quick tunnel
> for your demo — restart it right before presenting and paste the fresh
> URL into your Streamlit secrets. Many student projects do exactly this;
> it's a completely valid shortcut for a course deadline.

---

## Step 5 — Run both as background services (so they survive reboots)

Create two systemd services so `pi_server.py` and `cloudflared` start
automatically and keep running:

```bash
sudo nano /etc/systemd/system/pi-api.service
```
```ini
[Unit]
Description=Pi Security API
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/project/pi_server.py
WorkingDirectory=/home/pi/project
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo nano /etc/systemd/system/cloudflared-tunnel.service
```
```ini
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
ExecStart=/usr/bin/cloudflared tunnel run pi-security-project
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

Enable both:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pi-api cloudflared-tunnel
sudo systemctl start pi-api cloudflared-tunnel
```

Now even if the Pi reboots (power cut, etc), both come back automatically —
your dashboard link keeps working without you touching the Pi.

---

## RAM impact summary

| Process | Approx RAM |
|---|---|
| `pi_server.py` (FastAPI/uvicorn, idle) | ~30–50 MB |
| `cloudflared` tunnel daemon | ~15–25 MB |
| **Total added to your Pi** | **~50–75 MB** |

This is far lighter than running Streamlit on the Pi (~600 MB), and both
processes do almost nothing until a request actually comes in from your
cloud dashboard.
