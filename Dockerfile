FROM arm64v8/debian:bookworm

# =========================================
# Add RPi apt repo for picamera2
# =========================================
RUN apt-get update && apt-get install -y --no-install-recommends gnupg curl \
    && echo "deb http://archive.raspberrypi.org/debian/ bookworm main" > /etc/apt/sources.list.d/raspi.list \
    && apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 82B129927FA3303E

# =========================================
# Upgrade base system to match RPi repo
# =========================================
RUN apt-get update && apt-get -y upgrade

# =========================================
# System dependencies + picamera2
# =========================================
RUN apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    python3-picamera2 \
    python3-numpy \
    python3-opencv \
    build-essential \
    cmake \
    espeak-ng \
    espeak-ng-data \
    libespeak-ng-dev \
    alsa-utils \
    neofetch \
    && apt-get clean \
    && apt-get autoremove \
    && rm -rf /var/cache/apt/archives/* \
    && rm -rf /var/lib/apt/lists/*

# =========================================
# Working directory
# =========================================
WORKDIR /app

# =========================================
# Limit dlib compilation to 1 core to prevent OOM
# =========================================
# ENV DLIB_NUM_THREADS=1
# ENV MAKEFLAGS="-j1"

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