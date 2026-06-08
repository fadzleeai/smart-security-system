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
# CHECK known_faces
# =========================================

FACE_COUNT=$(ls known_faces/*.jpg known_faces/*.png 2>/dev/null | wc -l)

if [ "$FACE_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}⚠ No faces registered yet.${RESET}"
    read -p "  Register a face now? (y/n): " reg
    if [ "$reg" = "y" ]; then
        docker compose -f docker-compose.yml -f docker-compose.rpi.yml run --rm register
    fi
else
    echo -e "${GREEN}✓ ${FACE_COUNT} face(s) registered${RESET}"
fi

# =========================================
# BUILD IF NEEDED
# =========================================

if [ ! "$(docker images -q smart_security 2>/dev/null)" ]; then
    echo -e "\n${YELLOW}Building Docker image (first time, this takes a while)...${RESET}"
    docker compose build
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
echo -e "  Web dashboard: ${GREEN}http://${IP}:5000${RESET}"
echo -e "  Password:      ${GREEN}admin123${RESET}"
echo ""
echo -e "  Admin panel:   ${YELLOW}bash admin.sh${RESET}"
echo -e "  Stop system:   ${YELLOW}bash stop.sh${RESET}"
echo -e "  View logs:     ${YELLOW}docker compose logs -f security${RESET}"
echo -e "${YELLOW}========================================${RESET}\n"