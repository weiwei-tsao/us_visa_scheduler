#!/bin/bash

# Exit codes from visa.py
EXIT_WORK_LIMIT=0
EXIT_BAN=2
EXIT_NETWORK=3

# Cooldown times (seconds)
BAN_COOLDOWN=14400      # 4 hours
(sleep 5m)
NETWORK_COOLDOWN=300    # 5 minutes
CRASH_COOLDOWN=60       # 1 minute

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Ensure logs directory exists
mkdir -p logs

while true; do
    log "Starting Visa Scheduler..."
    ./venv/bin/python visa.py
    EXIT_CODE=$?
    
    case $EXIT_CODE in
        $EXIT_WORK_LIMIT)
            log "Work limit reached. Restarting immediately..."
            # No sleep, loop continues
            ;;
        $EXIT_BAN)
            log "BAN DETECTED. Sleeping for 4 hours..."
            sleep $BAN_COOLDOWN
            ;;
        $EXIT_NETWORK)
            log "Network issues/Max retries. Sleeping for 5 minutes..."
            sleep $NETWORK_COOLDOWN
            ;;
        *)
            log "Unexpected exit/Crash (Code $EXIT_CODE). Sleeping 1 min..."
            sleep $CRASH_COOLDOWN
            ;;
    esac
done
