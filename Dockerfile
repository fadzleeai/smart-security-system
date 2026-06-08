FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
    libv4l-dev \
    v4l-utils \
    espeak \
    espeak-data \
    libespeak-dev \
    alsa-utils \
    curl \
    python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://raw.githubusercontent.com/dylanaraps/neofetch/master/neofetch \
       -o /usr/local/bin/neofetch \
    && chmod +x /usr/local/bin/neofetch

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p known_faces logs strangers

CMD ["python", "main.py"]