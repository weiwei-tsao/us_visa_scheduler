#!/bin/bash
# Log cleanup script for US Visa Scheduler
# Compresses old logs and removes logs older than 30 days

LOG_DIR="${1:-logs}"
DAYS_TO_KEEP=30

echo "Cleaning up logs in $LOG_DIR..."

# Compress logs older than 7 days (except already compressed)
find "$LOG_DIR" -name "*.log" -type f -mtime +7 ! -name "*.gz" -exec gzip {} \;
find "$LOG_DIR" -name "*.txt" -type f -mtime +7 ! -name "*.gz" -exec gzip {} \;

# Remove compressed logs older than 30 days
find "$LOG_DIR" -name "*.gz" -type f -mtime +$DAYS_TO_KEEP -delete

# Remove empty log files
find "$LOG_DIR" -name "*.log" -type f -empty -delete

# Show current log sizes
echo ""
echo "Current log sizes:"
du -sh "$LOG_DIR"/* 2>/dev/null | sort -h

echo ""
echo "Cleanup complete."
