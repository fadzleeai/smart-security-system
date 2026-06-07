# =========================================
# Base image: Python 3.11 slim (multi-arch)
# Works on both Windows x64 (dev) and RPi 4 (arm64)
# =========================================
FROM python:3.11-slim

# =========================================
# System dependencies
# =========================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tools for dlib/face_recognition
    build-essential \
    cmake \
    # OpenCV dependencies
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
    # Camera support
    libv4l-dev \
    v4l-utils \
    # Audio / TTS
    espeak \
    espeak-data \
    libespeak-dev \
    alsa-utils \
    # neofetch (removed from trixie, install via curl)
    curl \
    # GPIO
    python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    # Install neofetch manually from GitHub
    && curl -fsSL https://raw.githubusercontent.com/dylanaraps/neofetch/master/neofetch \
       -o /usr/local/bin/neofetch \
    && chmod +x /usr/local/bin/neofetch

# =========================================
# Working directory
# =========================================
WORKDIR /app

# =========================================
# Install Python dependencies
# =========================================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =========================================
# Copy source code
# =========================================
COPY . .

# =========================================
# Create directories
# =========================================
RUN mkdir -p known_faces logs

# =========================================
# Default command: run main security app
# =========================================
CMD ["python", "main.py"]