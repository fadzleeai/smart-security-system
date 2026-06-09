FROM arm64v8/debian:bookworm

# =========================================
# Add RPi apt repo for picamera2
# =========================================
RUN apt-get update && apt-get install -y --no-install-recommends gnupg curl \
    && echo "deb http://archive.raspberrypi.org/debian/ bookworm main" > /etc/apt/sources.list.d/raspi.list \
    && apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 82B129927FA3303E \
    && apt-get update

# =========================================
# System dependencies + picamera2
# =========================================
RUN apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-picamera2 \
    python3-numpy \
    python3-opencv \
    build-essential \
    cmake \
    espeak \
    espeak-data \
    libespeak-dev \
    alsa-utils \
    neofetch \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# =========================================
# Working directory
# =========================================
WORKDIR /app

# =========================================
# Python dependencies
# =========================================
COPY requirements.txt .
RUN pip install --break-system-packages --no-cache-dir -r requirements.txt

# =========================================
# Copy source code
# =========================================
COPY . .

RUN mkdir -p known_faces logs strangers

CMD ["python3", "main.py"]