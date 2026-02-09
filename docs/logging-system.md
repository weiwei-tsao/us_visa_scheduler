# Structured Logging System

## Overview

The visa scheduler uses a structured JSON logging system for:
- Machine-parseable log analysis
- Sensitive data auto-redaction
- Automatic log rotation with compression
- Error categorization by type

## Log Files

| File | Content | Rotation |
|------|---------|----------|
| `logs/visa_scheduler.json.log` | Structured JSON entries | 10MB, 5 backups, gzip |
| `logs/visa_scheduler.error.log` | Errors only (text) | 5MB, 3 backups |
| `logs/pm2-out.log` | PM2 stdout | via pm2-logrotate |
| `logs/pm2-error.log` | PM2 stderr | via pm2-logrotate |

## Log Categories

```
SESSION   - Login, session expiry, relogin
BOOKING   - Date queries, reschedule attempts
NETWORK   - HTTP errors, timeouts
PROXY     - Proxy rotation, health
BAN       - Rate limiting detection
SELENIUM  - WebDriver errors
SYSTEM    - Startup, shutdown
HEARTBEAT - Periodic status
```

## JSON Log Format

```json
{
  "timestamp": "2026-02-02T10:30:00.123456",
  "level": "INFO",
  "category": "BOOKING",
  "message": "Found 5 available dates, earliest: 2026-02-10",
  "session_id": "20260202_103000",
  "request_count": 42,
  "operation": "get_dates",
  "extra": {"date_count": 5, "earliest": "2026-02-10"}
}
```

## Sensitive Data Redaction

Automatically redacted patterns:
- `_yatri_session` cookies
- `password` fields
- `token` / `api_key` values
- Long cookie strings (20+ chars)

Example: `_yatri_session=abc123` → `_yatri_session=[REDACTED]`

## Usage in Code

```python
from logger import get_logger, LogCategory

slog = get_logger()

# Session events
slog.login_success()
slog.session_expired("reason")

# Booking events
slog.dates_found(dates_list, earliest_date)
slog.reschedule_start(date)
slog.reschedule_success(date, time)
slog.reschedule_failed(date, reason)

# Error logging
slog.network_error("operation", exception, attempt, max_attempts)
slog.ban_detected("type", cooldown_minutes, consecutive_count)

# Generic
slog.info(LogCategory.SYSTEM, "message", key=value)
slog.warning(LogCategory.PROXY, "message")
slog.error(LogCategory.NETWORK, "message", error=exception)
```

## Log Analysis

```bash
# Summary
python log_analyzer.py

# Errors only
python log_analyzer.py --errors

# Last 24 hours
python log_analyzer.py --last 24h

# Reschedule timeline
python log_analyzer.py --reschedule

# JSON output
python log_analyzer.py --json
```

## PM2 Log Rotation Setup

```bash
# Install
pm2 install pm2-logrotate

# Configure
pm2 set pm2-logrotate:max_size 10M
pm2 set pm2-logrotate:retain 7
pm2 set pm2-logrotate:compress true
```

## Manual Cleanup

```bash
./scripts/cleanup_logs.sh logs/
```

Compresses logs older than 7 days, deletes logs older than 30 days.
