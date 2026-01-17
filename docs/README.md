# US Visa Scheduler - Comprehensive Codebase Analysis

## Table of Contents
- [Project Overview](#project-overview)
- [Architecture & Design](#architecture--design)
- [Project Structure](#project-structure)
- [Key Files & Components](#key-files--components)
- [Application Flow](#application-flow)
- [Visual Flow Diagram](#visual-flow-diagram)
- [Technology Stack](#technology-stack)
- [API Integration](#api-integration)
- [Configuration Guide](#configuration-guide)
- [Local Environment Setup](#local-environment-setup)
- [Usage Instructions](#usage-instructions)
- [Key Takeaways](#key-takeaways)
- [Security & Privacy](#security--privacy)
- [Monitoring & Logging](#monitoring--logging)
- [Anti-Detection Mechanisms](#anti-detection-mechanisms)
- [Limitations & Considerations](#limitations--considerations)

---

## Project Overview

**Purpose**: Automated bot for monitoring and rescheduling US visa appointments on usvisa-info.com

**Core Functionality**:
- Continuously monitors for earlier appointment dates
- Automatically reschedules when dates within target period are found
- Sends email notifications for all important events
- Implements anti-ban mechanisms and smart retry logic

**Use Case**: Helps visa applicants secure earlier appointment dates by automating the monitoring process 24/7.

---

## Architecture & Design

### Design Pattern
- **Architecture**: Monolithic single-file Python script
- **Execution Model**: Polling-based infinite loop
- **State Management**: Stateless (no database, only log files)
- **Automation Approach**: Hybrid (Selenium + Direct HTTP)

### Key Design Decisions

1. **Hybrid Automation Strategy**
   - **Selenium**: Handles authentication (bypasses reCAPTCHA)
   - **Direct HTTP**: Queries available dates (faster, less detectable)

2. **JavaScript Injection Pattern**
   - Uses `driver.execute_script()` to make XMLHttpRequest calls
   - Maintains browser session context for authenticity
   - Preserves cookies and headers automatically

3. **Anti-Detection Architecture**
   - Work/cooldown cycles prevent rate limiting
   - Ban detection through empty response monitoring
   - Realistic timing delays between actions

---

## Project Structure

```
us_visa_scheduler/
├── visa.py                 # Main application (282 lines)
├── embassy.py              # Embassy configurations (14 lines)
├── config.ini.example      # Configuration template
├── config.ini              # User configuration (gitignored)
├── requirements.txt        # Python dependencies
├── README.md              # User documentation
├── .gitignore             # Git ignore rules
├── pyvenv.cfg             # Virtual environment config
├── venv/                  # Python virtual environment
├── logs/                  # Log files directory
│   ├── .gitkeep           # Keeps directory in git
│   └── log_*.txt          # Daily log files (gitignored)
├── docs/                  # Documentation folder
│   └── README.md          # This file
```

---

## Key Files & Components

### 1. visa.py - Main Application

**Location**: `/Users/caoweiwei/Documents/14_Repositories/us_visa_scheduler/visa.py`

**Core Functions**:

| Function | Line Range | Purpose |
|----------|-----------|---------|
| `start_process()` | 52-78 | Handles login and authentication |
| `get_date()` | 92-109 | Fetches available appointment dates via API |
| `get_time(date)` | 112-129 | Gets available time slots for a date |
| `get_available_date(dates)` | 132-147 | Filters dates by target period |
| `reschedule(date)` | 150-191 | Performs rescheduling via HTTP POST |
| `send_notification(title, msg)` | 194-211 | Sends email via SendGrid |
| `auto_action()` | 80-89 | Generic Selenium form helper |
| `is_logged_in()` | 40-49 | Validates authentication status |
| `info_logger()` | 28-37 | Writes to daily log files |

**Main Loop**: Lines 214-282
- Infinite polling loop
- Ban detection and recovery
- Work/cooldown cycle management
- Automatic rescheduling
- Comprehensive exception handling

### 2. embassy.py - Embassy Configuration

**Location**: `/Users/caoweiwei/Documents/14_Repositories/us_visa_scheduler/embassy.py`

**Structure**:
```python
Embassies = {
    "embassy-code": ["country-code", facility_id, "continue_button_text"],
}
```

**Supported Locations**:
- **Armenia**: Yerevan (facility_id: 122)
- **Colombia**: Bogotá (facility_id: 25)
- **Canada**: Calgary (89), Halifax (90), Montreal (91), Ottawa (92), Quebec City (93), Toronto (94), Vancouver (95)

### 3. config.ini - User Configuration

**Location**: `/Users/caoweiwei/Documents/14_Repositories/us_visa_scheduler/config.ini`

**Configuration Sections**:

#### [PERSONAL_INFO]
```ini
USERNAME = account@gmail.com           # usvisa-info.com login email
PASSWORD = account_pass                 # Account password
SCHEDULE_ID = 99999999                 # From reschedule URL
PRIOD_START = 2023-03-20               # Target period start date
PRIOD_END = 2023-06-01                 # Target period end date
YOUR_EMBASSY = en-ca                   # Embassy code from embassy.py
```

#### [CHROMEDRIVER]
```ini
LOCAL_USE = True                       # Use local Chrome vs Selenium Grid
HUB_ADDRESS = http://localhost:9515    # Selenium Grid URL (if LOCAL_USE=False)
```

#### [NOTIFICATION]
```ini
SENDGRID_API_KEY =                     # SendGrid API key (optional)
SENDGRID_EMAIL_SENDER =                # Verified sender email (optional)
TELEGRAM_BOT_TOKEN =                   # Telegram bot token (optional)
TELEGRAM_CHAT_ID =                     # Telegram chat ID (optional)
```

#### [TIME]
```ini
RETRY_TIME = 60                        # Seconds between date checks
WORK_LIMIT_TIME = 1.5                  # Hours before mandatory rest
WORK_COOLDOWN_TIME = 2.25              # Hours to rest after work limit
BAN_COOLDOWN_TIME = 5                  # Hours to wait if banned
```

### 4. requirements.txt - Dependencies

**Location**: `/Users/caoweiwei/Documents/14_Repositories/us_visa_scheduler/requirements.txt`

```
selenium==4.19.0           # Web automation framework
webdriver-manager==4.0.1   # Automatic ChromeDriver management
requests==2.27.1           # HTTP client library
sendgrid==6.9.7            # Email notification service
```

---

## Application Flow

### Phase 1: Initialization
```
Load config.ini
    ↓
Parse embassy configuration from embassy.py
    ↓
Initialize Chrome WebDriver (local or remote)
    ↓
Build URLs and authentication headers
    ↓
Start logging session
```

### Phase 2: Authentication (Selenium)
```
Navigate to usvisa-info.com sign-in page
    ↓
Wait for page load
    ↓
Auto-fill email and password fields
    ↓
Accept privacy policy checkbox
    ↓
Submit login form
    ↓
Wait for redirect confirmation
    ↓
Verify login success
```

### Phase 3: Monitoring Loop (Infinite)
```
Make API request for available dates
    ↓
    ├─→ [No dates returned] → BAN DETECTED
    │       ↓
    │   Send ban notification
    │       ↓
    │   Logout from session
    │       ↓
    │   Sleep for BAN_COOLDOWN_TIME (5 hours)
    │       ↓
    │   Re-login and restart
    │
    ├─→ [Dates returned] → Filter by target period
            ↓
            ├─→ [No match] → Log results
            │                    ↓
            │                Check work time limit
            │                    ↓
            │                Sleep RETRY_TIME (60s)
            │                    ↓
            │                Continue loop
            │
            └─→ [Match found] → Get time slot
                                    ↓
                                POST reschedule request
                                    ↓
                                Send success/fail notification
                                    ↓
                                EXIT (mission complete)
```

### Phase 4: Work/Cooldown Management
```
Check elapsed work time
    ↓
    ├─→ [< WORK_LIMIT_TIME] → Continue working
    │
    └─→ [≥ WORK_LIMIT_TIME] → Send cooldown notification
                                   ↓
                               Sleep WORK_COOLDOWN_TIME (2.25 hours)
                                   ↓
                               Reset work timer
                                   ↓
                               Continue loop
```

---

## Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION START                         │
│  1. Load config.ini                                          │
│  2. Initialize Chrome WebDriver                              │
│  3. Parse embassy configuration                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│               LOGIN PHASE (Selenium)                         │
│  • Navigate to usvisa-info.com                               │
│  • Auto-fill email/password                                  │
│  • Accept privacy policy                                     │
│  • Submit form & verify login                                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│          MAIN MONITORING LOOP (Infinite)                     │
│                                                              │
│  ┌────────────────────────────────────────────┐             │
│  │ 1. API Request for Available Dates         │             │
│  │    (JavaScript injection via Selenium)     │             │
│  └─────┬──────────────────────────────────────┘             │
│        │                                                     │
│  ┌─────▼──────────────────────┐                             │
│  │ Dates List Empty?          │                             │
│  │ (Ban Detection)            │                             │
│  └─┬──────────────────────┬───┘                             │
│    │ YES (BANNED)         │ NO (OK)                         │
│    │                      │                                 │
│    │                      ▼                                 │
│    │              ┌───────────────────┐                     │
│    │              │ Filter by Period  │                     │
│    │              │ (PRIOD_START/END) │                     │
│    │              └───┬───────────┬───┘                     │
│    │                  │           │                         │
│    │             FOUND│           │NO MATCH                 │
│    │                  │           │                         │
│    │                  ▼           ▼                         │
│    │           ┌──────────┐  ┌────────────┐                │
│    │           │Get Time  │  │Sleep 60s   │                │
│    │           │Slot      │  │(RETRY_TIME)│                │
│    │           └────┬─────┘  └─────┬──────┘                │
│    │                │               │                       │
│    │                ▼               │                       │
│    │         ┌────────────┐         │                       │
│    │         │POST        │         │                       │
│    │         │Reschedule  │         │                       │
│    │         └─────┬──────┘         │                       │
│    │               │                │                       │
│    │               ▼                │                       │
│    │         ┌──────────┐           │                       │
│    │         │Send Email│           │                       │
│    │         │& EXIT    │           │                       │
│    │         └──────────┘           │                       │
│    │                                │                       │
│    ▼                                │                       │
│  ┌──────────────────┐               │                       │
│  │ Send Ban Alert   │               │                       │
│  │ Logout           │               │                       │
│  │ Sleep 5 hours    │◄──────────────┘                       │
│  │ Re-login         │   (Work Limit Check)                  │
│  └─────┬────────────┘                                       │
│        │                                                     │
│        └─────────────────────────────────────────────────┐  │
│                                                           │  │
└───────────────────────────────────────────────────────────┼──┘
                                                            │
                                                            └──► Loop continues
```

---

## Technology Stack

### Core Technologies
```
Python 3.10.11
├── Selenium 4.19.0        # Browser automation
│   ├── trio 0.31.0        # Async I/O support
│   └── trio-websocket     # WebSocket protocol
├── WebDriver Manager 4.0.1 # Auto ChromeDriver updates
├── Requests 2.27.1        # HTTP client
│   ├── urllib3 1.26.20    # HTTP library
│   ├── certifi            # SSL certificates
│   └── charset-normalizer # Character encoding
└── SendGrid 6.9.7         # Email service
    ├── python-http-client # HTTP wrapper
    └── starkbank-ecdsa    # Cryptography
```

### Runtime Environment
- **Browser**: Google Chrome 143.0.7499.193
- **Driver**: ChromeDriver (auto-managed)
- **OS**: macOS (Darwin 22.6.0)
- **Config Format**: INI (ConfigParser)

---

## API Integration

### usvisa-info.com Endpoints

#### 1. Get Available Dates
```
Endpoint: /{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment/days/{FACILITY_ID}.json
Method: GET (via JavaScript XMLHttpRequest)
Response: [{"date": "2023-06-15", "business_day": true}, ...]
```

#### 2. Get Time Slots
```
Endpoint: /{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment/times/{FACILITY_ID}.json?date={date}
Method: GET (via JavaScript XMLHttpRequest)
Response: {"available_times": ["09:00", "10:30", ...]}
```

#### 3. Reschedule Appointment
```
Endpoint: /{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment
Method: POST
Headers:
  - User-Agent: Mozilla/5.0...
  - Cookie: _yatri_session={session_token}
  - Referer: {APPOINTMENT_URL}
  - Content-Type: application/json
Body:
  {
    "appointment[consulate_appointment][facility_id]": FACILITY_ID,
    "appointment[consulate_appointment][date]": "2023-06-15",
    "appointment[consulate_appointment][time]": "09:00"
  }
```

### Authentication Flow
1. Selenium performs login → Obtains `_yatri_session` cookie
2. Cookie injected into JavaScript context → XMLHttpRequest uses it
3. Cookie added to HTTP headers → POST requests authenticated

---

## Configuration Guide

### Required Settings

#### 1. Get Your Schedule ID
1. Log into usvisa-info.com
2. Navigate to reschedule page
3. Copy number from URL:
   ```
   https://ais.usvisa-info.com/en-am/niv/schedule/{SCHEDULE_ID}/appointment
   ```
4. Add to config.ini: `SCHEDULE_ID = 12345678`

#### 2. Choose Embassy Code
Check `embassy.py` for available locations:
```python
"en-am": ["am", 122, "Continue"],  # Armenia - Yerevan
"en-co": ["co", 25, "Continue"],   # Colombia - Bogotá
"en-ca": ["ca", 89, "Continue"],   # Canada - Calgary
```
Add to config.ini: `YOUR_EMBASSY = en-ca`

#### 3. Set Target Period
Choose your desired appointment date range:
```ini
PRIOD_START = 2026-02-01
PRIOD_END = 2026-06-01
```

### Optional Settings

#### Email Notifications (SendGrid)
1. Sign up at [sendgrid.com](https://sendgrid.com/)
2. Create API key
3. Verify sender email
4. Add to config.ini:
   ```ini
   SENDGRID_API_KEY = SG.xxxxxxxxxxxxxxx
   SENDGRID_EMAIL_SENDER = verified@yourdomain.com
   ```

#### Telegram Bot Notifications
1. Open Telegram and talk to [@BotFather](https://t.me/BotFather)
2. Send `/newbot` command and follow instructions to create your bot
3. Copy the bot token provided by BotFather
4. Get your chat ID:
   - Method 1: Talk to [@userinfobot](https://t.me/userinfobot) - it will show your chat ID
   - Method 2: Send a message to your bot, then visit:
     ```
     https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
     ```
     Look for `"chat":{"id":123456789}` in the response
5. Add to config.ini:
   ```ini
   TELEGRAM_BOT_TOKEN = 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_CHAT_ID = 123456789
   ```

#### Timing Customization
```ini
RETRY_TIME = 60              # Check every 60 seconds
WORK_LIMIT_TIME = 1.5        # Work for 1.5 hours
WORK_COOLDOWN_TIME = 2.25    # Rest for 2.25 hours
BAN_COOLDOWN_TIME = 5        # Wait 5 hours if banned
```

---

## Local Environment Setup

### Prerequisites
- Python 3.9+ installed
- Google Chrome browser
- Active US visa appointment
- Account on usvisa-info.com

### Installation Steps

#### 1. Clone Repository
```bash
cd /path/to/us_visa_scheduler
```

#### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

Expected output:
```
Successfully installed:
  - selenium-4.19.0
  - webdriver-manager-4.0.1
  - requests-2.27.1
  - sendgrid-6.9.7
  - [+ 18 dependency packages]
```

#### 4. Create Configuration File
```bash
cp config.ini.example config.ini
```

#### 5. Edit Configuration
```bash
# Use your preferred editor
nano config.ini
# or
code config.ini
```

Fill in required fields:
- USERNAME
- PASSWORD
- SCHEDULE_ID
- PRIOD_START / PRIOD_END
- YOUR_EMBASSY

#### 6. Verify Chrome Installation
```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --version

# Linux
google-chrome --version

# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --version
```

### Setup Verification

Run a quick test:
```bash
python3 -c "import selenium; print('Selenium:', selenium.__version__)"
```

Expected: `Selenium: 4.19.0`

---

## Usage Instructions

### Starting the Bot

#### 1. Activate Virtual Environment
```bash
cd /path/to/us_visa_scheduler
source venv/bin/activate
```

#### 2. Run the Script
```bash
python3 visa.py
```

### What Happens Next

1. **Chrome Opens**: Browser window launches automatically
2. **Login Process**: Bot navigates to sign-in page and logs in
3. **Monitoring Starts**: Console shows real-time status updates
4. **Continuous Checking**: Bot polls for dates every RETRY_TIME seconds
5. **Auto-Reschedule**: When match found, reschedules automatically
6. **Notification Sent**: Email alert (if configured)
7. **Logging**: Creates `log_YYYY-MM-DD.txt` files

### Console Output Example
```
[2026-01-16 10:30:15] Starting visa appointment scheduler...
[2026-01-16 10:30:20] Logging in to usvisa-info.com...
[2026-01-16 10:30:35] Login successful!
[2026-01-16 10:30:40] Checking for available dates... (Attempt #1)
[2026-01-16 10:30:42] Available dates: ['2026-07-15', '2026-08-20']
[2026-01-16 10:30:42] No dates in target period (2026-02-01 to 2026-06-01)
[2026-01-16 10:31:42] Checking for available dates... (Attempt #2)
...
```

### Stopping the Bot
- Press `Ctrl+C` to stop
- Bot will attempt graceful shutdown
- Browser window will close

---

## Key Takeaways

### Strengths
1. **Hybrid Automation**: Smart combination of Selenium + HTTP requests
2. **Anti-Ban Protection**: Work limits, cooldowns, ban detection
3. **Email Notifications**: Real-time alerts for all events
4. **Auto-Recovery**: Handles bans and errors gracefully
5. **Configurable**: All parameters externalized to config.ini
6. **Logging**: Comprehensive daily logs for debugging
7. **Auto-Driver Management**: webdriver-manager handles ChromeDriver updates

### Architecture Highlights
- **Polling-based**: Simple, reliable monitoring approach
- **Stateless**: No database complexity
- **Single-file**: Easy to understand and modify
- **Configuration-driven**: User-specific data externalized
- **Resilient**: Broad exception handling with recovery

### Recent Updates (Git History)
- Updated to Selenium 4.19.0
- Fixed SendGrid integration
- Added rescheduling notifications
- Updated login selectors for site changes
- Removed PHP email sender (esender.php)

---

## Security & Privacy

### Sensitive Data Protection

#### Gitignored Files
```gitignore
config.ini          # Contains credentials
logs/*.txt          # Log files may contain personal info
__pycache__/        # Python cache
venv/               # Virtual environment
```

#### Credentials in config.ini
- **USERNAME**: usvisa-info.com email
- **PASSWORD**: Plain text password (consider encryption)
- **SCHEDULE_ID**: Personal appointment identifier
- **SENDGRID_API_KEY**: Email service credentials
- **TELEGRAM_BOT_TOKEN**: Telegram bot authentication token

### Security Recommendations
1. **Never commit config.ini** to version control
2. **Use strong passwords** for usvisa-info.com account
3. **Keep SendGrid API key secure** (treat like password)
4. **Review log files** before sharing (may contain personal data)
5. **Run on trusted network** (avoid public WiFi)
6. **Consider VPN** if running for extended periods

---

## Monitoring & Logging

### Log File Structure

**Location**: `./logs/log_YYYY-MM-DD.txt`

**Format**:
```
[YYYY-MM-DD HH:MM:SS] Event description
[2026-01-16 10:30:15] Starting scheduler...
[2026-01-16 10:30:40] Request count: 1
[2026-01-16 10:30:42] Available dates: ['2026-07-15']
[2026-01-16 10:30:42] No match found
[2026-01-16 10:31:42] Request count: 2
...
```

### Logged Events
- Application start/stop
- Login success/failure
- Request counts
- Available dates found
- Target period matches
- Reschedule attempts
- Work/cooldown cycles
- Ban detections
- Error messages
- Notification sends

### Monitoring Best Practices
1. **Check logs daily** for errors or unusual patterns
2. **Monitor work time** to ensure cooldowns working
3. **Track request counts** to avoid rate limiting
4. **Review available dates** to adjust target period if needed

---

## Anti-Detection Mechanisms

### 1. Work/Cooldown Cycles
```python
# Work for 1.5 hours, then rest for 2.25 hours
WORK_LIMIT_TIME = 1.5      # Hours of continuous work
WORK_COOLDOWN_TIME = 2.25  # Hours of rest
```

**Purpose**: Mimics human behavior, avoids rate limiting

### 2. Ban Detection
```python
if not dates:
    # Empty list indicates temporary ban
    send_notification("Banned", "Empty response detected")
    logout()
    sleep(BAN_COOLDOWN_TIME * 3600)  # 5 hours
    login()
```

**Triggers**: Empty date list response from API

### 3. Realistic Timing
```python
STEP_TIME = 1  # Seconds between actions
RETRY_TIME = 60  # Seconds between date checks
```

**Purpose**: Delays between actions appear more human

### 4. Session Maintenance
- Uses real browser (Chrome) via Selenium
- Maintains cookies naturally
- Proper HTTP headers (User-Agent, Referer)
- JavaScript execution in browser context

### 5. Graceful Degradation
- Continues operation despite errors
- Auto-recovery from bans
- Notification instead of crashing

---

## Limitations & Considerations

### Current Limitations

1. **Single-User Design**
   - No multi-user support
   - Can't monitor multiple appointments simultaneously
   - One config.ini per instance

2. **No Proxy Support**
   - Direct connection to usvisa-info.com
   - IP may be flagged with excessive requests
   - Consider VPN for additional protection

3. **Hard-Coded Embassy List**
   - Limited to embassies in embassy.py
   - Adding new locations requires code changes
   - No dynamic embassy discovery

4. **Browser Dependency**
   - Requires Chrome installation
   - ChromeDriver compatibility issues possible
   - Headless mode not implemented

5. **Stateless Operation**
   - No persistence beyond log files
   - Restart loses current work cycle progress
   - No historical analytics

6. **Limited Error Handling**
   - Generic exception catch may hide issues
   - No retry logic for failed reschedules
   - Network errors not specifically handled

### Potential Improvements

1. **Multi-Embassy Support**: Monitor multiple locations simultaneously
2. **Proxy Rotation**: Avoid IP-based rate limiting
3. **Headless Mode**: Run without visible browser window
4. **Database Integration**: Track historical appointment availability
5. **Additional Notifications**: SMS, Slack, Discord integrations
6. **Retry Logic**: Attempt reschedule multiple times on failure
7. **Configuration Validation**: Verify config.ini on startup
8. **Encrypted Credentials**: Secure password storage
9. **Web Dashboard**: Real-time monitoring UI

---

## Troubleshooting

### Common Issues

#### 1. Login Fails
**Symptoms**: Bot can't login, stuck on sign-in page

**Solutions**:
- Verify USERNAME and PASSWORD in config.ini
- Check for reCAPTCHA (may need manual intervention)
- Update login selectors if site changed (visa.py:56-65)

#### 2. ChromeDriver Issues
**Symptoms**: "ChromeDriver not found" or version mismatch

**Solutions**:
```bash
# webdriver-manager should auto-fix, but if not:
pip install --upgrade webdriver-manager
```

#### 3. No Dates Found
**Symptoms**: Always returns empty date list

**Solutions**:
- Verify SCHEDULE_ID is correct
- Check YOUR_EMBASSY matches your appointment
- Ensure facility_id in embassy.py is correct
- May be temporarily banned (wait BAN_COOLDOWN_TIME)

#### 4. SendGrid Errors
**Symptoms**: Email notifications not working

**Solutions**:
- Verify SENDGRID_API_KEY is valid
- Confirm sender email is verified in SendGrid
- Check SendGrid dashboard for blocked sends
- Test API key with curl command

#### 5. Ban Detected
**Symptoms**: Bot reports ban, enters long sleep

**Solutions**:
- Wait full BAN_COOLDOWN_TIME (5 hours)
- Increase RETRY_TIME to reduce request frequency
- Increase WORK_LIMIT_TIME to reduce logout/login cycles
- Consider using VPN

---

## File Paths Reference

### Key Files
- **Main Script**: `/Users/caoweiwei/Documents/14_Repositories/us_visa_scheduler/visa.py`
- **Embassy Config**: `/Users/caoweiwei/Documents/14_Repositories/us_visa_scheduler/embassy.py`
- **User Config**: `/Users/caoweiwei/Documents/14_Repositories/us_visa_scheduler/config.ini`
- **Config Template**: `/Users/caoweiwei/Documents/14_Repositories/us_visa_scheduler/config.ini.example`
- **Dependencies**: `/Users/caoweiwei/Documents/14_Repositories/us_visa_scheduler/requirements.txt`
- **Documentation**: `/Users/caoweiwei/Documents/14_Repositories/us_visa_scheduler/README.md`

### Generated Files
- **Virtual Environment**: `./venv/`
- **Daily Logs**: `./logs/log_YYYY-MM-DD.txt`
- **Python Cache**: `./__pycache__/`

---

## Contributing

### Development Setup
1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Make changes and test thoroughly
4. Commit: `git commit -m "Add feature"`
5. Push: `git push origin feature-name`
6. Open Pull Request

### Code Style
- Follow PEP 8 guidelines
- Add comments for complex logic
- Update documentation for new features
- Test with different embassy configurations

---

## License

This project is open source. Please check the repository for license details.

---

## Support & Contact

For issues and feature requests:
- GitHub Issues: [Repository URL]
- Documentation: This file + main README.md

---

## Appendix: Technical Details

### Date Filtering Logic
```python
def get_available_date(dates):
    priod_start = config.get('PERSONAL_INFO', 'PRIOD_START')
    priod_end = config.get('PERSONAL_INFO', 'PRIOD_END')

    for d in dates:
        date = d.get('date')
        if priod_start <= date <= priod_end:
            return date
    return None
```

### JavaScript Injection Pattern
```python
def get_date():
    script = f"return fetch('{DATE_URL}').then(r => r.json())"
    dates = driver.execute_script(script)
    return dates
```

### Session Cookie Management
```python
session = driver.get_cookies()
cookies = '; '.join([f"{c['name']}={c['value']}" for c in session])
headers = {'Cookie': cookies}
response = requests.post(url, headers=headers, data=data)
```

---

**Document Version**: 1.0
**Last Updated**: 2026-01-16
**Generated By**: Claude Code (Automated Codebase Analysis)
