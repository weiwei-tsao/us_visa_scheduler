#!/bin/bash

echo "=== PM2 Status ==="
pm2 status

echo -e "\n=== Last 5 App Log Entries ==="
tail -n 5 logs/log_$(date +%Y-%m-%d).txt 2>/dev/null || echo "No log file for today"

echo -e "\n=== Chrome Processes ==="
ps aux | grep -i chrome | grep -v grep | wc -l | xargs echo "Chrome instances:"

echo -e "\n=== Recent PM2 Restarts ==="
pm2 show visa-scheduler | grep "restarts" || echo "No restart info"
