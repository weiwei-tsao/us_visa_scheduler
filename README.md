# US Visa Appointment Sniper

An intelligent automation bot for monitoring and rescheduling US visa appointments on `usvisa-info.com` to secure earlier appointment dates.

## Key Features

| Feature | Description |
|---------|-------------|
| **Stealth Mode** | Uses `undetected-chromedriver` to bypass Cloudflare/bot detection |
| **Graduated Ban Detection** | Smart cooldown system (5min → 30min → 2hr → 4hr) reduces false positive downtime |
| **Three-Tier Recovery** | Page refresh → Full relogin → Proxy rotation for maximum resilience |
| **Proxy Rotation** | Supports HTTP/HTTPS/SOCKS5 proxies with automatic rotation on ban |
| **Multi-Channel Notifications** | Real-time alerts via SendGrid email and Telegram |
| **Structured Logging** | JSON logs with automatic sensitive data redaction and rotation |
| **Headless Support** | Run on servers without a display |

## Quick Start

### Prerequisites

- Python 3.8+
- Chrome/Chromium browser
- An existing US visa appointment on usvisa-info.com

### Installation

```bash
# Clone the repository
git clone https://github.com/weiwei-tsao/us_visa_appointment_sniper.git
cd us_visa_appointment_sniper

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip3 install -r requirements.txt

# Configure
cp config.ini.example config.ini
# Edit config.ini with your credentials
```

### Running

```bash
# Option 1: Direct execution
./run_visa.sh

# Option 2: PM2 process manager (recommended for production)
pm2 start ecosystem.config.js
pm2 save && pm2 startup
```

## Configuration

Edit `config.ini` with your settings:

```ini
[PERSONAL_INFO]
USERNAME = your_email@example.com
PASSWORD = your_password
SCHEDULE_ID = 12345678              # From your appointment URL
PRIOD_START = 2025-02-15            # Earliest acceptable date
PRIOD_END = 2026-12-31              # Latest acceptable date
YOUR_EMBASSY = en-ca-tor            # Embassy code (see below)

[BEHAVIOR]
HEADLESS = False                    # Run without visible browser
STEP_DELAY = 0.5                    # Delay between steps (seconds)

[TIME]
RETRY_TIME_L_BOUND = 60             # Min check interval (seconds)
RETRY_TIME_U_BOUND = 120            # Max check interval (seconds)
WORK_LIMIT_TIME = 0.75              # Hours before clean restart

[NOTIFICATION]
SENDGRID_API_KEY =                  # Optional: SendGrid API key
TELEGRAM_BOT_TOKEN =                # Optional: Telegram bot token
TELEGRAM_CHAT_ID =                  # Optional: Your chat ID

[PROXY]
ENABLED = False
PROXY_LIST =
    http://user:pass@proxy1:8080
    socks5://proxy2:1080
ROTATION_STRATEGY = on_ban          # round_robin | random | on_ban
```

### Supported Embassies

| Code | Location |
|------|----------|
| `en-ca-tor` | Canada - Toronto |
| `en-ca-van` | Canada - Vancouver |
| `en-ca-cal` | Canada - Calgary |
| `en-ca-mon` | Canada - Montreal |
| `en-ca-ott` | Canada - Ottawa |
| `en-ca-hal` | Canada - Halifax |
| `en-ca-que` | Canada - Quebec |
| `en-am-yer` | Armenia - Yerevan |
| `es-co-bog` | Colombia - Bogota |

### Polling Strategies

| Strategy | Interval | Checks/Hour | Risk Level |
|----------|----------|-------------|------------|
| Conservative | 111-300s | ~18 | Low |
| Moderate | 60-120s | ~40 | Medium |
| Aggressive | 30-60s | ~80 | High (proxy recommended) |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    run_visa.sh (Process Wrapper)            │
│            Handles exit codes, cooldowns, restarts          │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                      visa.py (Core Engine)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Config &     │  │ Ban Detection│  │ Main Loop    │      │
│  │ Validation   │  │ & Recovery   │  │ & Scheduling │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┬───────────────────┐
        │                │                │                   │
   ┌────▼────┐    ┌──────▼──────┐   ┌─────▼─────┐    ┌───────▼───────┐
   │ logger  │    │ proxy_      │   │ embassy   │    │ Notifications │
   │ .py     │    │ manager.py  │   │ .py       │    │ (SendGrid/TG) │
   └─────────┘    └─────────────┘   └───────────┘    └───────────────┘
```

## Core Mechanisms

### Ban Detection & Graduated Cooldown

The system distinguishes between temporary glitches and real bans:

| Consecutive Empty Responses | Cooldown | Action |
|-----------------------------|----------|--------|
| 1st | 5 minutes | Continue monitoring |
| 2nd | 30 minutes | Continue monitoring |
| 3rd | 2 hours | Continue monitoring |
| 4th+ or HTTP 403/429 | 4 hours | Exit (or rotate proxy) |

### Three-Tier Recovery Strategy

When a reschedule attempt fails:

1. **Level 1 - Page Refresh** (~2s): Quick recovery for transient issues
2. **Level 2 - Full Relogin** (~5s): Session restoration
3. **Level 3 - Proxy Rotation** (~10s): Only when Cloudflare detected

### Proxy Rotation Strategies

| Strategy | Behavior | Best For |
|----------|----------|----------|
| `round_robin` | Sequential rotation | Even proxy usage |
| `random` | Random selection | Pattern avoidance |
| `on_ban` | Rotate only on ban | Proxy conservation |

## Monitoring

### PM2 Commands

```bash
pm2 status                          # Check process status
pm2 logs visa-scheduler             # View live logs
pm2 logs visa-scheduler --lines 100 # View last 100 lines
pm2 restart visa-scheduler          # Manual restart
./status.sh                         # Quick status dashboard
```

### Log Analysis

```bash
# Analyze structured JSON logs
python log_analyzer.py              # Summary
python log_analyzer.py --errors     # Errors only
python log_analyzer.py --last 24h   # Last 24 hours
python log_analyzer.py --reschedule # Reschedule timeline
```

### Log Files

| File | Description |
|------|-------------|
| `logs/visa_scheduler.json.log` | Structured JSON (10MB rotation, gzip) |
| `logs/visa_scheduler.error.log` | Error-only logs |
| `logs/pm2-out.log` | PM2 stdout |
| `logs/.last_earliest_date` | Persistent state (last notified date) |

## Notification Events

| Event | Trigger |
|-------|---------|
| SCHEDULER STARTED | Session begins |
| HEARTBEAT | Every 20 requests |
| DATES AVAILABLE | New earliest date found |
| Rescheduling Started | Target date found in range |
| SUCCESS/FAIL/NO_SLOTS | Booking result |
| BAN WARNING/DETECTED | Rate limiting events |

## Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=. --cov-report=term-missing

# Run specific test file
pytest tests/test_reschedule_retry.py -v
```

## Project Structure

```
us_visa_appointment_sniper/
├── visa.py                 # Core automation engine (1,143 lines)
├── logger.py               # Structured logging system (593 lines)
├── proxy_manager.py        # Proxy management (447 lines)
├── embassy.py              # Embassy definitions
├── log_analyzer.py         # JSON log analysis
├── config.ini.example      # Configuration template
├── requirements.txt        # Python dependencies
├── run_visa.sh             # Process wrapper script
├── ecosystem.config.js     # PM2 configuration
├── tests/                  # Test suite (18 files, 100+ tests)
│   ├── test_reschedule_retry.py
│   ├── test_ban_detection.py
│   ├── test_logger.py
│   └── ...
├── logs/                   # Runtime logs
└── docs/                   # Additional documentation
    ├── logging-system.md
    ├── reschedule-retry-fix.md
    └── ...
```

## Anti-Detection Mechanisms

1. **Undetected ChromeDriver**: Bypasses Cloudflare and bot detection
2. **JavaScript XMLHttpRequest**: API calls within browser context
3. **Randomized Intervals**: Prevents pattern detection
4. **Session Rotation**: Periodic restarts create fresh sessions
5. **Graduated Cooldowns**: Reduces detection from aggressive retries

## Troubleshooting

### ChromeDriver Issues
Ensure Chrome browser is installed and up to date. The script automatically falls back to standard Selenium if `undetected-chromedriver` fails.

### Session Expiration
The bot automatically detects session expiration and re-authenticates.

### Rate Limiting
If you see frequent empty responses:
1. Increase `RETRY_TIME_L_BOUND` and `RETRY_TIME_U_BOUND`
2. Enable proxy rotation
3. Check logs for ban patterns: `python log_analyzer.py --errors`

## License

MIT License - See [LICENSE](LICENSE) for details.

## Disclaimer

This tool is for personal use only. Users are responsible for compliance with the terms of service of usvisa-info.com. Use at your own risk.
