# US Visa Scheduler

An automated bot for continuously monitoring and rescheduling US VISA appointments on `usvisa-info.com` to secure earlier appointment dates.

## Features

- **Stealth Mode**: Uses `undetected-chromedriver` ([visa.py:424-462](visa.py#L424-L462)) to bypass Cloudflare/bot detection
- **Headless Support**: Run on servers without a display (configurable in `config.ini`)
- **Graduated Ban Detection**: Smart cooldown system (5min → 30min → 2hr → 4hr) to reduce false positive downtime ([visa.py:104-200](visa.py#L104-L200))
- **Configurable Polling**: Adjust check frequency from conservative (18/hr) to aggressive (80/hr) with randomized intervals ([visa.py:957-962](visa.py#L957-L962))
- **Proxy Rotation**: Optional proxy support with automatic rotation on ban detection ([proxy_manager.py](proxy_manager.py))
- **Multi-Channel Notifications**: Email via SendGrid and Telegram bot notifications ([visa.py:539-563](visa.py#L539-L563))
- **Persistent State Tracking**: Reduces notification noise by tracking last notified earliest date ([visa.py:834-942](visa.py#L834-L942))
- **Session Monitoring**: Startup and heartbeat notifications every 20 requests ([visa.py:824-857](visa.py#L824-L857))

## Prerequisites

- Python 3.8+
- Chrome/Chromium browser installed
- An existing US VISA appointment on usvisa-info.com
- [Optional] SendGrid API key for email notifications
- [Optional] Telegram Bot token and Chat ID for Telegram notifications

## Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip3 install -r requirements.txt
```

### Dependencies

From [requirements.txt](requirements.txt):
- `selenium` - WebDriver automation
- `webdriver-manager` - Chrome driver management
- `requests` - HTTP library for notifications
- `sendgrid` - Email API client
- `undetected-chromedriver` - Stealth Chrome driver

## Configuration

```bash
cp config.ini.example config.ini
```

Edit `config.ini` with your settings. Configuration is loaded in [visa.py:43-100](visa.py#L43-L100).

### Personal Info Section

```ini
[PERSONAL_INFO]
USERNAME = your_email@example.com
PASSWORD = your_password
SCHEDULE_ID = 12345678
PRIOD_START = 2025-02-15
PRIOD_END = 2026-12-31
YOUR_EMBASSY = en-ca-tor
```

| Parameter | Description |
|-----------|-------------|
| `USERNAME` | Your usvisa-info.com account email |
| `PASSWORD` | Your usvisa-info.com account password |
| `SCHEDULE_ID` | Found in your appointment reschedule URL: `https://ais.usvisa-info.com/en-ca/niv/schedule/{SCHEDULE_ID}/appointment` |
| `PRIOD_START` | Earliest acceptable appointment date (YYYY-MM-DD) |
| `PRIOD_END` | Latest acceptable appointment date (YYYY-MM-DD) |
| `YOUR_EMBASSY` | Embassy code from [embassy.py](embassy.py) |

### Supported Embassies

Defined in [embassy.py](embassy.py):

| Code | Location | Facility ID |
|------|----------|-------------|
| `en-am-yer` | Armenia - Yerevan | 122 |
| `es-co-bog` | Colombia - Bogota | 25 |
| `en-ca-cal` | Canada - Calgary | 89 |
| `en-ca-hal` | Canada - Halifax | 90 |
| `en-ca-mon` | Canada - Montreal | 91 |
| `en-ca-ott` | Canada - Ottawa | 92 |
| `en-ca-que` | Canada - Quebec | 93 |
| `en-ca-tor` | Canada - Toronto | 94 |
| `en-ca-van` | Canada - Vancouver | 95 |

### ChromeDriver Section

```ini
[CHROMEDRIVER]
LOCAL_USE = True
HUB_ADDRESS = http://localhost:9515/wd/hub
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `LOCAL_USE` | `True` | Use local Chrome browser |
| `HUB_ADDRESS` | - | Remote WebDriver hub URL (only if `LOCAL_USE = False`) |

### Behavior Section

```ini
[BEHAVIOR]
HEADLESS = False
STEP_DELAY = 0.5
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `HEADLESS` | `False` | Run without visible browser window. **Warning**: May increase detection risk |
| `STEP_DELAY` | `0.5` | Delay between automation steps in seconds ([visa.py:588-597](visa.py#L588-L597)) |

### Notification Section

```ini
[NOTIFICATION]
SENDGRID_API_KEY =
SENDGRID_EMAIL_SENDER =
TELEGRAM_BOT_TOKEN =
TELEGRAM_CHAT_ID =
```

**Email Setup (SendGrid)**:
1. Create account at [sendgrid.com](https://sendgrid.com)
2. Generate API key
3. Set `SENDGRID_API_KEY` and `SENDGRID_EMAIL_SENDER`

**Telegram Setup**:
1. Message [@BotFather](https://t.me/BotFather) to create a bot and get token
2. Message [@userinfobot](https://t.me/userinfobot) to get your chat ID
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`

### Time Section

```ini
[TIME]
RETRY_TIME_L_BOUND = 60
RETRY_TIME_U_BOUND = 120
WORK_LIMIT_TIME = 0.75
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `RETRY_TIME_L_BOUND` | `111` | Lower bound for check interval (seconds) |
| `RETRY_TIME_U_BOUND` | `300` | Upper bound for check interval (seconds) |
| `WORK_LIMIT_TIME` | `0.75` | Runtime before clean restart (hours) |

**Recommended Polling Ranges**:
- **Conservative**: 111-300s (~18 checks/hour) - Safest
- **Moderate**: 60-120s (~40 checks/hour) - Balanced
- **Aggressive**: 30-60s (~80 checks/hour) - Proxy recommended

### Ban Detection Section

```ini
[BAN_DETECTION]
COOLDOWN_FIRST_EMPTY = 5
COOLDOWN_SECOND_EMPTY = 30
COOLDOWN_THIRD_EMPTY = 120
COOLDOWN_HARD_BAN = 240
```

Graduated cooldown logic implemented in [visa.py:104-200](visa.py#L104-L200):

| Consecutive Empty Responses | Cooldown | Action |
|-----------------------------|----------|--------|
| 1st | 5 minutes | Continue after cooldown |
| 2nd | 30 minutes | Continue after cooldown |
| 3rd | 2 hours | Continue after cooldown |
| 4th+ or HTTP 403/429 | Exit | Wait 4 hours (handled by wrapper) |

### Proxy Section

```ini
[PROXY]
ENABLED = False
PROXY_LIST =
    http://user:pass@proxy1.example.com:8080
    http://user:pass@proxy2.example.com:8080
    socks5://proxy3.example.com:1080
ROTATION_STRATEGY = on_ban
HEALTH_CHECK = False
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ENABLED` | `False` | Enable proxy rotation |
| `PROXY_LIST` | - | List of proxies (one per line) |
| `ROTATION_STRATEGY` | `on_ban` | `round_robin`, `random`, or `on_ban` |
| `HEALTH_CHECK` | `False` | Test proxy connectivity before use |

Proxy management implemented in [proxy_manager.py](proxy_manager.py). Supports:
- HTTP/HTTPS proxies
- SOCKS4/SOCKS5 proxies
- Authenticated proxies (via Chrome extension, [proxy_manager.py:230-310](proxy_manager.py#L230-L310))

## Running

### Option 1: Manual Execution (Development/Testing)

```bash
./run_visa.sh
```

The [run_visa.sh](run_visa.sh) wrapper script handles exit codes and implements intelligent restart logic:

| Exit Code | Meaning | Wrapper Action |
|-----------|---------|----------------|
| 0 | Work limit reached | Restart immediately |
| 2 | Ban detected | Wait 4 hours, then restart |
| 3 | Network error | Wait 5 minutes, then restart |
| Other | Crash/exception | Wait 1 minute, then restart |

Exit codes defined in [visa.py:30-33](visa.py#L30-L33).

### Option 2: PM2 Process Manager (Recommended)

PM2 provides automatic restart, crash recovery, and background execution.

#### Prerequisites

```bash
# Install Node.js (macOS)
brew install node

# Install PM2 globally
npm install -g pm2
```

#### Starting with PM2

```bash
# Start the script
pm2 start ecosystem.config.js

# Save process list (persists across reboots)
pm2 save

# Enable PM2 to start on system boot
pm2 startup
```

PM2 configuration in [ecosystem.config.js](ecosystem.config.js):
- Auto-restart on crash
- Memory limit: 500MB (restarts if Chrome exceeds)
- Logs to `logs/pm2-out.log` and `logs/pm2-error.log`
- Minimum uptime: 60 seconds before restart counts

#### Common PM2 Commands

```bash
pm2 status                          # Check status
pm2 logs visa-scheduler             # View live logs
pm2 logs visa-scheduler --lines 100 # View last 100 lines
pm2 restart visa-scheduler          # Manual restart
pm2 delete visa-scheduler           # Stop and remove
./status.sh                         # Quick status dashboard
```

## How It Works

### Main Execution Flow

The main loop runs in [visa.py:847-975](visa.py#L847-L975):

1. **Fetch Available Dates**: Retrieves dates via JavaScript XMLHttpRequest ([visa.py:687-721](visa.py#L687-L721))
2. **Ban Detection**: Checks for empty responses or HTTP errors ([visa.py:867-891](visa.py#L867-L891))
3. **Date Filtering**: Finds dates within target range ([visa.py:768-797](visa.py#L768-L797))
4. **Booking Attempt**: If matching date found, attempts reschedule ([visa.py:601-668](visa.py#L601-L668))
5. **Notification**: Sends alerts on status changes ([visa.py:539-563](visa.py#L539-L563))
6. **Work Limit Check**: Exits for restart after configured runtime ([visa.py:943-955](visa.py#L943-L955))

### Booking Flow

The `reschedule()` function in [visa.py:601-668](visa.py#L601-L668):

1. Fetch available time slots for the target date
2. Navigate to appointment page
3. Extract session cookie and authenticity token
4. POST booking request with form data
5. Check response for "successfully scheduled"

### API Endpoints Used

URLs constructed in [visa.py:407-411](visa.py#L407-L411):

| Endpoint | Purpose |
|----------|---------|
| `/niv/users/sign_in` | Authentication |
| `/niv/schedule/{ID}/appointment` | Reschedule page |
| `/niv/schedule/{ID}/appointment/days/{FACILITY}.json` | Available dates |
| `/niv/schedule/{ID}/appointment/times/{FACILITY}.json` | Time slots |

### Notification Events

| Event | Trigger | Location |
|-------|---------|----------|
| SCHEDULER STARTED | Session begins | [visa.py:827](visa.py#L827) |
| HEARTBEAT | Every 20 requests | [visa.py:857](visa.py#L857) |
| DATES AVAILABLE | New earliest date found | [visa.py:940](visa.py#L940) |
| Rescheduling Started | Target date found | [visa.py:905](visa.py#L905) |
| SUCCESS/FAIL/NO_SLOTS | Booking result | [visa.py:907](visa.py#L907) |
| BAN WARNING | 3+ empty responses | [visa.py:197](visa.py#L197) |
| BAN DETECTED | Hard ban | [visa.py:186](visa.py#L186) |

### Persistent State

The file `logs/.last_earliest_date` tracks the last notified earliest date to reduce notification noise. Implemented in [visa.py:834-942](visa.py#L834-L942).

## Anti-Detection Mechanisms

### 1. Undetected-ChromeDriver

Uses `undetected-chromedriver` to bypass Cloudflare detection. Falls back to standard Selenium if unavailable. See [visa.py:424-462](visa.py#L424-L462).

### 2. JavaScript XMLHttpRequest

API requests executed within browser context to mimic real browser behavior. See [visa.py:413-419](visa.py#L413-L419).

### 3. Randomized Polling

Request intervals randomized between configured bounds to prevent pattern detection. See [visa.py:957-962](visa.py#L957-L962).

### 4. Session Rotation

Work limit forces periodic restarts, creating new sessions and cookies. See [visa.py:950-955](visa.py#L950-L955).

### 5. Graduated Cooldowns

Smart cooldown distinguishes between real bans and false positives (temporary glitches, no available dates). See [visa.py:162-199](visa.py#L162-L199).

## Log Analysis

### Application Logs

Daily logs stored in `logs/log_YYYY-MM-DD.txt`. Analyze with:

```bash
python3 analyze_logs.py
```

Output from [analyze_logs.py](analyze_logs.py):
- Total unique dates found
- Earliest and latest dates
- Availability breakdown by month

### PM2 Execution Analysis

Analyze session patterns:

```bash
python3 analyze_pm2.py
```

Output from [analyze_pm2.py](analyze_pm2.py):
- Session start/end times
- Duration and request counts
- Re-login events
- Exit reasons

### Log Files

| File | Description |
|------|-------------|
| `logs/log_YYYY-MM-DD.txt` | Application logs |
| `logs/pm2-out.log` | PM2 standard output |
| `logs/pm2-error.log` | PM2 error output |
| `logs/.last_earliest_date` | Persistent state (last notified date) |

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_booking_flow.py -v

# Run with coverage
pytest tests/ --cov=.
```

Test suites in [tests/](tests/):
- `test_ban_detection.py` - Ban detection system
- `test_booking_flow.py` - Booking workflow edge cases
- `test_booking_execution.py` - End-to-end booking
- `test_config_validation.py` - Configuration validation
- `test_integration.py` - Full system integration
- `test_proxy_integration.py` - Proxy functionality
- `test_proxy_manager.py` - Proxy manager unit tests
- `test_session_management.py` - Session lifecycle

## Project Structure

```
us_visa_scheduler/
├── visa.py                 # Main application (979 lines)
├── embassy.py              # Embassy definitions
├── proxy_manager.py        # Proxy management system
├── analyze_logs.py         # Log analysis utility
├── analyze_pm2.py          # PM2 execution analysis
├── config.ini              # Active configuration
├── config.ini.example      # Configuration template
├── requirements.txt        # Python dependencies
├── run_visa.sh             # Bash wrapper script
├── ecosystem.config.js     # PM2 process manager config
├── status.sh               # Quick status checker
├── logs/                   # Log files and persistent state
│   ├── log_YYYY-MM-DD.txt  # Daily application logs
│   ├── pm2-out.log         # PM2 stdout
│   ├── pm2-error.log       # PM2 stderr
│   └── .last_earliest_date # Persistent state file
├── tests/                  # Test suite
│   ├── conftest.py         # Pytest fixtures
│   ├── test_*.py           # Test files
│   └── mocks/              # Mock response data
└── docs/                   # Additional documentation
```

## Troubleshooting

### ChromeDriver Issues

If `undetected-chromedriver` fails, the script falls back to standard Selenium ([visa.py:455-462](visa.py#L455-L462)). Ensure Chrome browser is installed and up to date.

### Session Expiration

The bot automatically detects session expiration and re-authenticates ([visa.py:670-685](visa.py#L670-L685)).

### Rate Limiting

If you see frequent empty responses:
1. Increase `RETRY_TIME_L_BOUND` and `RETRY_TIME_U_BOUND`
2. Enable proxy rotation
3. Check `logs/` for patterns

### Configuration Validation

Configuration is validated on startup ([visa.py:341-404](visa.py#L341-L404)). Errors are logged with specific messages about what's wrong.
