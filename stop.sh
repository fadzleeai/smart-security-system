#!/bin/bash

GREEN='\033[92m'
YELLOW='\033[93m'
RESET='\033[0m'

echo -e "${YELLOW}Stopping Smart Security...${RESET}"
docker compose -f docker-compose.yml -f docker-compose.rpi.yml down
echo -e "${GREEN}✓ All services stopped.${RESET}"