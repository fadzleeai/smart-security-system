#!/bin/bash
 
docker run --rm -it \
  -v ./config.json:/app/config.json \
  -v ./known_faces:/app/known_faces \
  -v ./logs:/app/logs \
  smart_security python3 src/admin.py