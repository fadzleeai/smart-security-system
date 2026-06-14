#!/bin/bash

# =========================================
# Smart Security — RPi Startup Script
# Usage: bash start.sh
# =========================================

GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[31m'
RESET='\033[0m'

echo -e "${GREEN}"
cat logo.txt 2>/dev/null || echo "Smart Security System"
echo -e "${RESET}"

echo -e "${YELLOW}========================================${RESET}"
echo -e "${YELLOW}   Smart Security — Starting Up${RESET}"
echo -e "${YELLOW}========================================${RESET}\n"

# =========================================
# CHECK DOCKER
# =========================================

if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not found. Install it first:${RESET}"
    echo "  curl -fsSL https://get.docker.com | sh"
    exit 1
fi

echo -e "${GREEN}✓ Docker found${RESET}"

# =========================================
# CHECK IMAGE EXISTS
# Option A (default): load pre-built image transferred from laptop
# Option B: build directly on Pi (slow — uncomment below)
# =========================================

if [ ! "$(docker images -q smart_security 2>/dev/null)" ]; then
    echo -e "${YELLOW}⚠ smart_security image not found.${RESET}"

    # ---------------------------------------------------------
    # Option A — load pre-built image (recommended)
    # Transfer image from laptop first:
    #   docker save smart_security -o smart_security.tar
    #   scp smart_security.tar admin@<pi-ip>:~/
    # Then load it:
    echo -e "  ${YELLOW}Attempting to load from smart_security.tar...${RESET}"
    if [ -f smart_security.tar ]; then
        docker load < smart_security.tar
    else
        echo -e "${RED}✗ smart_security.tar not found.${RESET}"
        echo -e "  Transfer the image to this machine first."
        # ---------------------------------------------------------
        # Option B — build on Pi (uncomment if you prefer)
        # WARNING: first build is very slow (dlib compiles from source)
        # echo -e "${YELLOW}Building image on Pi (this will take a while)...${RESET}"
        # docker compose build
        # ---------------------------------------------------------
        exit 1
    fi
fi

echo -e "${GREEN}✓ Image ready${RESET}"

# =========================================
# CHECK known_faces
# =========================================

FACE_COUNT=$(ls known_faces/*.jpg known_faces/*.png 2>/dev/null | wc -l)

if [ "$FACE_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}⚠ No faces registered yet. Register via the web dashboard after startup.${RESET}"
else
    echo -e "${GREEN}✓ ${FACE_COUNT} face(s) registered${RESET}"
fi

# =========================================
# START SERVICES
# =========================================

echo -e "\n${GREEN}Starting security + web services...${RESET}\n"

docker compose -f docker-compose.yml -f docker-compose.rpi.yml up -d security web

# =========================================
# SHOW STATUS
# =========================================

sleep 2

echo -e "\n${YELLOW}========================================${RESET}"
echo -e "${GREEN}✓ System is live!${RESET}"
echo ""

# Get RPi IP
IP=$(hostname -I | awk '{print $1}')
echo -e "  Web dashboard: ${GREEN}https://${IP}:5000${RESET}"
echo -e "  Password:      ${GREEN}admin123${RESET}"
echo ""
echo -e "  Admin panel:   ${YELLOW}bash admin.sh${RESET}"
echo -e "  Stop system:   ${YELLOW}bash stop.sh${RESET}"
echo -e "  View logs:     ${YELLOW}docker compose logs -f security${RESET}"
echo -e "${YELLOW}========================================${RESET}\n"