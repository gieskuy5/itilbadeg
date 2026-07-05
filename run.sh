#!/bin/bash
# Interlink auto-restart wrapper
cd "$(dirname "$0")"
while true; do
    echo "[$(date '+%H:%M:%S')] Starting Interlink bot..."
    python3 main.py 2>&1 | tee -a interlink.log
    echo "[$(date '+%H:%M:%S')] Bot exited (code $?), restarting in 10s..."
    sleep 10
done
