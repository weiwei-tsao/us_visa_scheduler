# visa_rescheduler

The visa_rescheduler is a bot for US VISA (usvisa-info.com) appointment rescheduling. This bot can help you reschedule your appointment to your desired time period.

**New Features**:
-   **Stealth Mode**: Uses `undetected-chromedriver` to mimic human behavior and avoid detection.
-   **Headless Support**: Can now run on servers without a display.


## Prerequisites

- Having a US VISA appointment scheduled already.
- [Optional] API token from Sendgrid (for email notifications)
- [Optional] Telegram Bot token and Chat ID (for Telegram notifications)

## Installation

```
pip3 install -r requirements.txt
```

## Configuration

```
cp config.ini.example config.ini
```

## Update your config.ini file (Username, Password, Targeted Dates, Timing)
```
[PERSONAL_INFO]
; Account and current appointment info from https://ais.usvisa-info.com
USERNAME = 
PASSWORD = 
; Find SCHEDULE_ID in re-schedule page link:
; https://ais.usvisa-info.com/en-am/niv/schedule/{SCHEDULE_ID}/appointment
SCHEDULE_ID = 
; Target Period:
PRIOD_START = 2025-02-15
PRIOD_END = 2026-12-31
; Change "en-ca-tor", based on your embassy Abbreviation in embassy.py list.
YOUR_EMBASSY = en-ca-tor

[CHROMEDRIVER]
; Details for the script to control Chrome
LOCAL_USE = True
; Optional: HUB_ADDRESS is mandatory only when LOCAL_USE = False
HUB_ADDRESS = http://localhost:9515/wd/hub

[BEHAVIOR]
; Headless mode: run without opening a visible browser window (default: False)
; WARNING: Headless mode may increase detection risk
HEADLESS = False
; Delay between steps in seconds (default: 0.5)
STEP_DELAY = 0.5


[NOTIFICATION]
; Get email notifications via https://sendgrid.com/ (optional)
SENDGRID_API_KEY =
SENDGRID_EMAIL_SENDER =

; Get Telegram notifications via Telegram Bot (optional)
; To setup: 1) Talk to @BotFather on Telegram to create a bot and get token
;           2) Talk to @userinfobot to get your chat ID, or message your bot
;              and visit https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN =
TELEGRAM_CHAT_ID =

[TIME]
; Time between retries/checks for available dates (seconds)
; Randomized interval bounds (5 min - 15 min)
RETRY_TIME_L_BOUND = 300
RETRY_TIME_U_BOUND = 900
; Script runtime limit before clean restart (hours)
; 0.75 hours = 45 minutes
WORK_LIMIT_TIME = 0.75
; Ban cooldown is handled by the wrapper script (run_visa.sh), but kept here for reference
BAN_COOLDOWN_TIME = 24

```

## Running

### Option 1: Manual Execution (Development/Testing)

```bash
./run_visa.sh
```

This runs the script in the foreground. The terminal must stay open and the script will stop if the terminal is closed.

### Option 2: PM2 Process Manager (Recommended for Production)

PM2 provides automatic restart, crash recovery, and background execution without needing to keep the terminal open.

#### Prerequisites
- Node.js and npm installed
- PM2 installed globally

#### Installation

```bash
# Install Node.js (if not already installed)
brew install node

# Install PM2 globally
npm install -g pm2
```

#### Starting with PM2

```bash
# Start the script with PM2
pm2 start ecosystem.config.js

# Save PM2 process list (persists across reboots)
pm2 save

# Optional: Enable PM2 to start on system boot
pm2 startup
```

#### PM2 Benefits

- **Relative interval restarts**: Script exits after `WORK_LIMIT_TIME` hours (configured in config.ini), PM2 restarts immediately. This creates relative intervals from script start, not fixed clock times.
- **Crash recovery**: Automatically restarts if script crashes
- **Background execution**: No need to keep terminal open
- **Memory protection**: Restarts if Chrome uses >500MB
- **Easy monitoring**: Check status with `pm2 status`
- **No fixed schedule**: Restarts happen relative to when script starts, ensuring continuous coverage even after maintenance or bans

#### Common PM2 Commands

```bash
# Check status
pm2 status

# View live logs
pm2 logs visa-scheduler

# View last 100 lines
pm2 logs visa-scheduler --lines 100

# Manually restart
pm2 restart visa-scheduler

# Stop and remove
pm2 delete visa-scheduler

# Quick status dashboard
./status.sh
```


## Log Analysis

To analyze the log files and see a summary of all available appointment dates found by the bot:

```bash
python3 analyze_logs.py
```

This script parses all `log_*.txt` files in the `logs/` directory and outputs:
- Total unique dates found
- Earliest and latest dates
- Availability breakdown by month
- A complete list of all unique dates


## PM2 Log Analysis

To analyze the PM2 logs and understand bot execution patterns (sessions, durations, sleeps):

```bash
python3 analyze_pm2.py
```

This script parses `logs/pm2-out.log` and outputs a table of detected sessions, including start/end times, duration, and outcomes (e.g., Running, Sleeping).

#### PM2 Log Files

PM2 creates separate log files in addition to the application logs:
- `./logs/pm2-out.log` - Standard output (print statements)
- `./logs/pm2-error.log` - Errors and exceptions
- `./logs/log_YYYY-MM-DD.txt` - Application logs (unchanged)

For more details, see [docs/PM2_DESIGN.md](docs/PM2_DESIGN.md) and [docs/SAFE_ARCHITECTURE_UPDATE.md](docs/SAFE_ARCHITECTURE_UPDATE.md)
