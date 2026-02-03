import time
import json
import requests
import configparser
import os
import sys
import random
from datetime import datetime

from logger import init_logger, get_logger, LogCategory, OperationType

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
try:
    import undetected_chromedriver as uc
except ImportError:
    uc = None


from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.common.by import By

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from embassy import *
from proxy_manager import ProxyManager, load_proxy_config

# Exit Codes
EXIT_WORK_LIMIT = 0
EXIT_BAN = 2
EXIT_NETWORK = 3

# Default ban detection cooldowns (in minutes)
DEFAULT_BAN_COOLDOWNS = {
    'first': 5,      # First empty response: 5 minutes
    'second': 30,    # Second consecutive: 30 minutes
    'third': 120,    # Third consecutive: 2 hours
    'hard_ban': 240  # HTTP 403/429: 4 hours
}

config = configparser.ConfigParser()
config.read('config.ini')

# Personal Info:
USERNAME = config['PERSONAL_INFO']['USERNAME']
PASSWORD = config['PERSONAL_INFO']['PASSWORD']
SCHEDULE_ID = config['PERSONAL_INFO']['SCHEDULE_ID']
PRIOD_START = config['PERSONAL_INFO']['PRIOD_START']
PRIOD_END = config['PERSONAL_INFO']['PRIOD_END']
YOUR_EMBASSY = config['PERSONAL_INFO']['YOUR_EMBASSY'] 
EMBASSY = Embassies[YOUR_EMBASSY][0]
FACILITY_ID = Embassies[YOUR_EMBASSY][1]
REGEX_CONTINUE = Embassies[YOUR_EMBASSY][2]

# Notification:
SENDGRID_API_KEY = config['NOTIFICATION']['SENDGRID_API_KEY']
SENDGRID_EMAIL_SENDER = config['NOTIFICATION']['SENDGRID_EMAIL_SENDER']
TELEGRAM_BOT_TOKEN = config['NOTIFICATION'].get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = config['NOTIFICATION'].get('TELEGRAM_CHAT_ID', '')

# Time Section:
minute = 60
hour = 60 * minute
STEP_TIME = 0.5
if 'BEHAVIOR' in config:
    HEADLESS = config['BEHAVIOR'].getboolean('HEADLESS')
    STEP_TIME = config['BEHAVIOR'].getfloat('STEP_DELAY')
else:
    HEADLESS = False

# Randomized Retry Logic

# Randomized Retry Logic
RETRY_TIME_L_BOUND = config['TIME'].getfloat('RETRY_TIME_L_BOUND')
RETRY_TIME_U_BOUND = config['TIME'].getfloat('RETRY_TIME_U_BOUND')

# Work Limits
WORK_LIMIT_TIME = config['TIME'].getfloat('WORK_LIMIT_TIME')

# CHROMEDRIVER
LOCAL_USE = config['CHROMEDRIVER'].getboolean('LOCAL_USE')
HUB_ADDRESS = config['CHROMEDRIVER']['HUB_ADDRESS']

# Ban Detection Config (with defaults for backward compatibility)
def load_ban_detection_config(cfg):
    """Load ban detection config with defaults for backward compatibility."""
    defaults = DEFAULT_BAN_COOLDOWNS.copy()
    if 'BAN_DETECTION' in cfg:
        defaults['first'] = cfg['BAN_DETECTION'].getint('COOLDOWN_FIRST_EMPTY', defaults['first'])
        defaults['second'] = cfg['BAN_DETECTION'].getint('COOLDOWN_SECOND_EMPTY', defaults['second'])
        defaults['third'] = cfg['BAN_DETECTION'].getint('COOLDOWN_THIRD_EMPTY', defaults['third'])
        defaults['hard_ban'] = cfg['BAN_DETECTION'].getint('COOLDOWN_HARD_BAN', defaults['hard_ban'])
    return defaults

BAN_COOLDOWNS = load_ban_detection_config(config)

# Proxy Configuration
PROXY_ENABLED, PROXY_MANAGER = load_proxy_config(config)

def is_hard_ban_response(http_status, response_text):
    """
    Detect if response indicates a hard ban (Cloudflare block).

    Args:
        http_status: HTTP status code (403, 429, etc.)
        response_text: Response body text

    Returns:
        True if hard ban detected, False otherwise
    """
    # HTTP 403 or 429 are definite ban signals
    if http_status in (403, 429):
        return True

    # Check for Cloudflare signatures in response
    ban_signatures = [
        'you have been blocked',
        'error 1015',
        'rate limited',
        'access denied',
        'cf-ray'  # Cloudflare ray ID in response
    ]

    response_lower = response_text.lower()
    return any(sig in response_lower for sig in ban_signatures)

def get_ban_cooldown(consecutive_empty_count, http_status, cooldown_config, retry_after=None):
    """
    Calculate cooldown duration based on ban signals.

    Args:
        consecutive_empty_count: Number of consecutive empty responses
        http_status: HTTP status code from response
        cooldown_config: Dict with cooldown values in minutes
        retry_after: Optional Retry-After header value in seconds

    Returns:
        Cooldown duration in seconds, or -1 to signal exit
    """
    # HTTP 403/429 = hard ban, use long cooldown
    if http_status in (403, 429):
        # If Retry-After header present, use it
        if retry_after:
            return retry_after
        return cooldown_config['hard_ban'] * 60

    # Graduated response based on consecutive empty count
    if consecutive_empty_count == 1:
        return cooldown_config['first'] * 60
    elif consecutive_empty_count == 2:
        return cooldown_config['second'] * 60
    elif consecutive_empty_count == 3:
        return cooldown_config['third'] * 60
    else:
        # 4+ consecutive empties = give up, exit
        return -1

def handle_empty_response(consecutive_count, cooldown_config):
    """
    Handle empty response with graduated cooldown.

    Args:
        consecutive_count: Number of consecutive empty responses
        cooldown_config: Dict with cooldown values

    Returns:
        Dict with 'action' ('sleep' or 'exit') and 'duration' in seconds
    """
    slog = get_logger()
    cooldown = get_ban_cooldown(
        consecutive_empty_count=consecutive_count,
        http_status=200,  # Empty array comes with 200
        cooldown_config=cooldown_config
    )

    if cooldown == -1:
        # Too many consecutive empties, exit
        slog.ban_detected("consecutive_empty", 0, consecutive_count)
        slog.error(LogCategory.BAN, f"{consecutive_count} consecutive empty responses. Likely banned. Exiting.")
        send_notification("BAN DETECTED", f"{consecutive_count} consecutive empty responses. Likely banned.")
        return {'action': 'exit', 'duration': 0}

    # Log the graduated response
    slog.ban_detected("empty_response", cooldown // 60, consecutive_count)

    # Only send notification on 3rd consecutive (warning before potential exit)
    if consecutive_count >= 3:
        send_notification("BAN WARNING", f"Multiple empty responses ({consecutive_count}). May be rate limited.")

    return {'action': 'sleep', 'duration': cooldown}


# Default retry time bounds (in seconds)
DEFAULT_RETRY_TIME_L_BOUND = 111
DEFAULT_RETRY_TIME_U_BOUND = 300


def validate_retry_time_config(lower_bound, upper_bound):
    """
    Validate retry time configuration bounds.

    Args:
        lower_bound: Lower bound for retry interval in seconds
        upper_bound: Upper bound for retry interval in seconds

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if lower_bound <= 0:
        errors.append("Lower bound must be greater than 0 seconds")

    if upper_bound <= 0:
        errors.append("Upper bound must be greater than 0 seconds")

    if lower_bound > upper_bound:
        errors.append("Lower bound cannot be greater than upper bound")

    return errors


def get_config_warnings(lower_bound, upper_bound, proxy_enabled,
                        sendgrid_configured=True, telegram_configured=True):
    """
    Get warnings for potentially risky configuration.

    Args:
        lower_bound: Lower bound for retry interval in seconds
        upper_bound: Upper bound for retry interval in seconds
        proxy_enabled: Whether proxy is enabled
        sendgrid_configured: Whether SendGrid notifications are configured
        telegram_configured: Whether Telegram notifications are configured

    Returns:
        List of warning messages
    """
    warnings = []

    # Aggressive polling warning (< 60s without proxy)
    if upper_bound < 60 and not proxy_enabled:
        warnings.append(
            "Aggressive polling interval detected (< 60s) without proxy. "
            "This increases ban risk. Consider using a proxy or increasing interval."
        )

    # No notifications configured
    if not sendgrid_configured and not telegram_configured:
        warnings.append(
            "No notification method configured. You won't be alerted "
            "when appointments become available."
        )

    return warnings


def validate_date_config(start_date, end_date):
    """
    Validate date configuration.

    Args:
        start_date: Start date string (YYYY-MM-DD format)
        end_date: End date string (YYYY-MM-DD format)

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Validate start date format
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        errors.append(f"Invalid start date format: '{start_date}'. Expected YYYY-MM-DD")
        start_dt = None

    # Validate end date format
    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        errors.append(f"Invalid end date format: '{end_date}'. Expected YYYY-MM-DD")
        end_dt = None

    # Validate date order
    if start_dt and end_dt and start_dt >= end_dt:
        errors.append("Start date must be before end date")

    return errors


def validate_embassy_config(embassy_code):
    """
    Validate embassy code against known embassies.

    Args:
        embassy_code: Embassy code string (e.g., 'en-ca-tor')

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    if embassy_code not in Embassies:
        errors.append(
            f"Invalid embassy code: '{embassy_code}'. "
            f"Valid codes: {', '.join(sorted(Embassies.keys()))}"
        )

    return errors


def get_retry_time_bounds(config):
    """
    Get retry time bounds from config with defaults.

    Args:
        config: ConfigParser object

    Returns:
        Tuple of (lower_bound, upper_bound) in seconds
    """
    lower = DEFAULT_RETRY_TIME_L_BOUND
    upper = DEFAULT_RETRY_TIME_U_BOUND

    if 'TIME' in config:
        lower = config['TIME'].getfloat('RETRY_TIME_L_BOUND', lower)
        upper = config['TIME'].getfloat('RETRY_TIME_U_BOUND', upper)

    return (int(lower), int(upper))


def validate_config(config):
    """
    Validate full configuration.

    Args:
        config: ConfigParser object

    Returns:
        Tuple of (errors, warnings) - both are lists of strings
    """
    errors = []
    warnings = []

    # Check required sections
    required_sections = ['PERSONAL_INFO']
    for section in required_sections:
        if section not in config:
            errors.append(f"Missing required config section: [{section}]")
            return (errors, warnings)  # Can't continue without PERSONAL_INFO

    # Validate personal info
    personal = config['PERSONAL_INFO']

    # Required fields
    required_fields = ['USERNAME', 'PASSWORD', 'SCHEDULE_ID', 'PRIOD_START', 'PRIOD_END', 'YOUR_EMBASSY']
    for field in required_fields:
        if field not in personal or not personal[field]:
            errors.append(f"Missing required field: PERSONAL_INFO.{field}")

    # Validate dates
    if 'PRIOD_START' in personal and 'PRIOD_END' in personal:
        date_errors = validate_date_config(personal['PRIOD_START'], personal['PRIOD_END'])
        errors.extend(date_errors)

    # Validate embassy
    if 'YOUR_EMBASSY' in personal:
        embassy_errors = validate_embassy_config(personal['YOUR_EMBASSY'])
        errors.extend(embassy_errors)

    # Validate retry time bounds
    lower, upper = get_retry_time_bounds(config)
    time_errors = validate_retry_time_config(lower, upper)
    errors.extend(time_errors)

    # Get warnings
    proxy_enabled = False
    if 'PROXY' in config:
        proxy_enabled = config['PROXY'].getboolean('ENABLED', False)
    sendgrid_configured = False
    telegram_configured = False
    if 'NOTIFICATION' in config:
        sendgrid_configured = bool(config['NOTIFICATION'].get('SENDGRID_API_KEY', ''))
        telegram_configured = bool(config['NOTIFICATION'].get('TELEGRAM_BOT_TOKEN', ''))

    config_warnings = get_config_warnings(
        lower_bound=lower,
        upper_bound=upper,
        proxy_enabled=proxy_enabled,
        sendgrid_configured=sendgrid_configured,
        telegram_configured=telegram_configured
    )
    warnings.extend(config_warnings)

    return (errors, warnings)


SIGN_IN_LINK = f"https://ais.usvisa-info.com/{EMBASSY}/niv/users/sign_in"
APPOINTMENT_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment"
DATE_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment/days/{FACILITY_ID}.json?appointments[expedite]=false"
TIME_URL = f"https://ais.usvisa-info.com/{EMBASSY}/niv/schedule/{SCHEDULE_ID}/appointment/times/{FACILITY_ID}.json?date=%s&appointments[expedite]=false"
SIGN_OUT_LINK = f"https://ais.usvisa-info.com/{EMBASSY}/niv/users/sign_out"

JS_SCRIPT = ("var req = new XMLHttpRequest();"
             f"req.open('GET', '%s', false);"
             "req.setRequestHeader('Accept', 'application/json, text/javascript, */*; q=0.01');"
             "req.setRequestHeader('X-Requested-With', 'XMLHttpRequest');"
             f"req.setRequestHeader('Cookie', '_yatri_session=%s');"
             "req.send(null);"
             "return req.responseText;")

driver = None
proxy_extension_path = None  # Track extension path for cleanup

def init_driver(proxy_manager=None):
    """
    Initialize Chrome WebDriver with optional proxy support.

    Args:
        proxy_manager: Optional ProxyManager instance for proxy support
    """
    global driver, proxy_extension_path
    slog = get_logger()

    # Get proxy configuration if enabled
    proxy_args = []
    proxy_extension = None

    if proxy_manager and proxy_manager.has_proxies:
        proxy = proxy_manager.get_proxy()
        if proxy:
            slog.info(LogCategory.PROXY, f"Using proxy: {proxy['host']}:{proxy['port']}")

            # Check if proxy requires authentication
            if proxy_manager.requires_auth_extension(proxy):
                slog.info(LogCategory.PROXY, "Creating authentication extension")
                proxy_extension = proxy_manager.create_proxy_auth_extension(proxy)
                proxy_extension_path = proxy_extension
            else:
                proxy_args = proxy_manager.get_chrome_options_args(proxy)

    if LOCAL_USE:
        # Try undetected-chromedriver first (Stealth Mode)
        if uc:
            try:
                options = webdriver.ChromeOptions()
                if HEADLESS:
                    options.add_argument('--headless')
                for arg in proxy_args:
                    options.add_argument(arg)
                if proxy_extension:
                    options.add_extension(proxy_extension)
                driver = uc.Chrome(options=options)
                slog.info(LogCategory.SELENIUM, "Initialized undetected-chromedriver (Stealth Mode)")
                return
            except Exception as e:
                slog.warning(LogCategory.SELENIUM, f"undetected-chromedriver failed: {e}, falling back to standard Selenium")

        # Fallback to standard Selenium
        try:
            options = webdriver.ChromeOptions()
            if HEADLESS:
                options.add_argument('--headless')
            for arg in proxy_args:
                options.add_argument(arg)
            if proxy_extension:
                options.add_extension(proxy_extension)
            driver = webdriver.Chrome(options=options)
            slog.info(LogCategory.SELENIUM, "Initialized standard Chrome driver")
        except Exception as e:
            slog.warning(LogCategory.SELENIUM, f"Standard Chrome failed: {e}, trying webdriver-manager")
            options = webdriver.ChromeOptions()
            if HEADLESS:
                options.add_argument('--headless')
            for arg in proxy_args:
                options.add_argument(arg)
            if proxy_extension:
                options.add_extension(proxy_extension)
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            slog.info(LogCategory.SELENIUM, "Initialized Chrome via webdriver-manager")
    else:
        options = webdriver.ChromeOptions()
        if HEADLESS:
            options.add_argument('--headless')
        for arg in proxy_args:
            options.add_argument(arg)
        if proxy_extension:
            options.add_extension(proxy_extension)
        driver = webdriver.Remote(command_executor=HUB_ADDRESS, options=options)
        slog.info(LogCategory.SELENIUM, f"Initialized remote Chrome at {HUB_ADDRESS}")


def rotate_proxy_and_restart():
    """
    Rotate to next proxy and restart the driver.

    Returns:
        True if successfully rotated, False if no more proxies available
    """
    global driver, PROXY_MANAGER
    slog = get_logger()

    if not PROXY_ENABLED or not PROXY_MANAGER:
        return False

    if not PROXY_MANAGER.has_proxies:
        slog.warning(LogCategory.PROXY, "No proxies configured")
        return False

    # Mark current proxy as potentially problematic and rotate
    current_proxy = PROXY_MANAGER.get_proxy()
    from_proxy = f"{current_proxy['host']}:{current_proxy['port']}" if current_proxy else "none"

    new_proxy = PROXY_MANAGER.rotate()
    if not new_proxy:
        slog.proxy_exhausted()
        return False

    to_proxy = f"{new_proxy['host']}:{new_proxy['port']}"
    slog.proxy_rotate(from_proxy, to_proxy, "ban_or_error")

    # Restart driver with new proxy
    try:
        if driver:
            driver.quit()
    except Exception:
        pass

    init_driver(PROXY_MANAGER)
    return True


def send_notification(title, msg):
    slog = get_logger()
    if SENDGRID_API_KEY:
        message = Mail(from_email=SENDGRID_EMAIL_SENDER, to_emails=USERNAME, subject=title, html_content=msg)
        try:
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)
            slog.info(LogCategory.SYSTEM, f"Email sent: {title}", http_status=response.status_code)
        except Exception as e:
            slog.error(LogCategory.NETWORK, f"SendGrid error: {e}", error=e)

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        def escape_html(text):
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        telegram_message = f"<b>{escape_html(title)}</b>\n\n{escape_html(msg)}"
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        telegram_data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": telegram_message,
            "parse_mode": "HTML"
        }
        try:
            requests.post(telegram_url, data=telegram_data, timeout=5)
            slog.info(LogCategory.SYSTEM, f"Telegram sent: {title}")
        except Exception as e:
            slog.error(LogCategory.NETWORK, f"Telegram error: {e}", error=e)

def auto_action(label, find_by, el_type, action, value, sleep_time=0):
    print("\t"+ label +":", end="")
    find_by_lower = find_by.lower()
    if find_by_lower == 'id':
        item = driver.find_element(By.ID, el_type)
    elif find_by_lower == 'name':
        item = driver.find_element(By.NAME, el_type)
    elif find_by_lower == 'class':
        item = driver.find_element(By.CLASS_NAME, el_type)
    elif find_by_lower == 'xpath':
        item = driver.find_element(By.XPATH, el_type)
    else:
        return 0
    action_lower = action.lower()
    if action_lower == 'send':
        item.send_keys(value)
    elif action_lower == 'click':
        item.click()
    else:
        return 0
    print("\t\tCheck!")
    if sleep_time:
        time.sleep(sleep_time)

def start_process():
    slog = get_logger()
    driver.get(SIGN_IN_LINK)
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "commit")))
    auto_action("Click bounce", "xpath", '//a[@class="down-arrow bounce"]', "click", "", STEP_TIME)
    auto_action("Email", "id", "user_email", "send", USERNAME, STEP_TIME)
    auto_action("Password", "id", "user_password", "send", PASSWORD, STEP_TIME)
    auto_action("Privacy", "class", "icheckbox", "click", "", STEP_TIME)
    auto_action("Enter Panel", "name", "commit", "click", "", STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(), '" + REGEX_CONTINUE + "')]")))
    slog.login_success()

def reschedule(date):
    """
    Attempt to reschedule appointment to the given date.

    Args:
        date: Target date string in YYYY-MM-DD format

    Returns:
        List of [status, message] where status is "SUCCESS", "FAIL", or "NO_SLOTS"
    """
    # FIXED: Handle None returned when no time slots available (race condition)
    appointment_time = get_time_with_retry(date)
    if not appointment_time:
        return ["NO_SLOTS", f"No time slots available for {date} - slot may have been taken"]

    driver.get(APPOINTMENT_URL)
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "authenticity_token")))

    # FIXED: Add null check for session cookie
    cookie = driver.get_cookie("_yatri_session")
    if not cookie:
        return ["FAIL", "Session cookie not found - session may have expired"]

    headers = {
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
        "Referer": APPOINTMENT_URL,
        "Cookie": "_yatri_session=" + cookie["value"]
    }

    data = {
        "appointments[consulate_appointment][facility_id]": FACILITY_ID,
        "appointments[consulate_appointment][date]": date,
        "appointments[consulate_appointment][time]": appointment_time,
    }

    # Required field - fail if not found
    try:
        data["authenticity_token"] = driver.find_element(by=By.NAME, value='authenticity_token').get_attribute('value')
    except Exception as e:
        return ["FAIL", f"Could not find authenticity token: {e}"]

    # FIXED: Replace bare except with specific exception handling
    # These are optional fields - log warning but continue
    from selenium.common.exceptions import NoSuchElementException
    optional_fields = ['utf8', 'confirmed_limit_message', 'use_consulate_appointment_capacity']
    for field in optional_fields:
        try:
            data[field] = driver.find_element(by=By.NAME, value=field).get_attribute('value')
        except NoSuchElementException:
            pass  # Optional field not present, continue

    # FIXED: Add timeout to prevent hanging indefinitely
    try:
        r = requests.post(APPOINTMENT_URL, headers=headers, data=data, timeout=30)
    except requests.exceptions.Timeout:
        return ["FAIL", f"Request timed out while booking {date} {appointment_time}"]
    except requests.exceptions.RequestException as e:
        return ["FAIL", f"Network error while booking: {e}"]

    # FIXED: Case-insensitive success detection
    slog = get_logger()
    response_lower = r.text.lower()
    if 'successfully scheduled' in response_lower:
        return ["SUCCESS", f"Rescheduled Successfully! {date} {appointment_time}"]
    else:
        # Log response body for debugging
        slog.warning(LogCategory.BOOKING, f"Failed response (status {r.status_code})",
                     http_status=r.status_code, response_preview=r.text[:300])
        return ["FAIL", f"Reschedule Failed!!! {date} {appointment_time} (HTTP {r.status_code})"]

def is_session_expired_error(error):
    error_str = str(error).lower()
    return any(x in error_str for x in ['expecting value', 'jsondecodeerror', 'empty response', '401', '403', 'unauthorized', 'session', 'expired'])

def relogin():
    slog = get_logger()
    try:
        slog.session_expired("API returned session error")
        slog.relogin_attempt(1, 1)
        try:
            driver.get(SIGN_OUT_LINK)
            time.sleep(STEP_TIME)
        except: pass
        start_process()
        slog.login_success()
        return True
    except Exception as e:
        slog.login_failed(e, 1, 1)
        return False

def get_date_with_retry(max_retries=3):
    """
    Fetch available appointment dates from the API.

    Args:
        max_retries: Maximum number of retry attempts

    Returns:
        List of available dates from API

    Raises:
        ValueError: If session expired or API returns invalid response
    """
    slog = get_logger()
    for attempt in range(max_retries):
        try:
            # FIXED: Add null check for session cookie
            cookie = driver.get_cookie("_yatri_session")
            if not cookie:
                raise ValueError("Session cookie not found - session may have expired")
            session = cookie["value"]

            script = JS_SCRIPT % (str(DATE_URL), session)
            content = driver.execute_script(script)
            if not content or content.strip() == '':
                raise ValueError("Empty response from API")
            return json.loads(content)
        except Exception as e:
            if is_session_expired_error(e) and attempt < max_retries - 1:
                if relogin(): continue
                else: raise
            elif isinstance(e, WebDriverException) and attempt < max_retries - 1:
                slog.network_error("get_dates", e, attempt + 1, max_retries)
                time.sleep(60) # Internal temporary network sleep
            else:
                raise

def get_time_with_retry(date, max_retries=3):
    """
    Fetch available time slots for a given date.

    Args:
        date: Date string in YYYY-MM-DD format
        max_retries: Maximum number of retry attempts

    Returns:
        First available time slot string, or None if no slots available

    Raises:
        ValueError: If API returns empty or invalid response after retries
    """
    slog = get_logger()
    for attempt in range(max_retries):
        try:
            time_url = TIME_URL % date

            # FIXED: Add null check for session cookie
            cookie = driver.get_cookie("_yatri_session")
            if not cookie:
                raise ValueError("Session cookie not found - session may have expired")
            session = cookie["value"]

            script = JS_SCRIPT % (str(time_url), session)
            content = driver.execute_script(script)
            if not content or content.strip() == '':
                raise ValueError("Empty response from API")
            data = json.loads(content)

            # FIXED: Validate available_times before accessing
            available_times = data.get("available_times")
            if not available_times:
                # No time slots available - slot may have been taken
                slog.warning(LogCategory.BOOKING, f"No time slots for {date} - slot may have been taken", date=date)
                return None

            # FIXED: Return FIRST time slot (earliest) instead of last
            return available_times[0]
        except Exception as e:
             if is_session_expired_error(e) and attempt < max_retries - 1:
                if relogin(): continue
                else: raise
             else: raise

def get_available_date(dates):
    """
    Find the first available date within the configured period.

    Args:
        dates: List of date objects (dicts with 'date' key or strings)

    Returns:
        First matching date string, or None if no dates in range
    """
    def is_in_period(date, PSD, PED):
        new_date = datetime.strptime(date, "%Y-%m-%d")
        # FIXED: Use inclusive boundaries (>= and <=) instead of strict (> and <)
        # This ensures dates on PRIOD_START and PRIOD_END are included
        return PSD <= new_date <= PED

    def extract_date(d):
        # Handle both dict format {"date": "..."} and string format "..."
        if isinstance(d, dict):
            return d.get('date')
        return d

    PED = datetime.strptime(PRIOD_END, "%Y-%m-%d")
    PSD = datetime.strptime(PRIOD_START, "%Y-%m-%d")
    for d in dates:
        date = extract_date(d)
        if date and is_in_period(date, PSD, PED):
            return date
    # No dates in target range - this is normal, not an error
    slog = get_logger()
    slog.info(LogCategory.BOOKING, f"No dates in target range ({PSD.date()} to {PED.date()})")
    return None

def cleanup_and_exit(exit_code):
    slog = get_logger()
    reasons = {
        EXIT_WORK_LIMIT: "work_limit_reached",
        EXIT_BAN: "ban_detected",
        EXIT_NETWORK: "network_error"
    }
    slog.system_shutdown(reasons.get(exit_code, "unknown"), exit_code)
    try:
        if driver:
            driver.quit()
    except:
        pass
    sys.exit(exit_code)

if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    # Initialize structured logger
    slog = init_logger(log_dir="logs", app_name="visa_scheduler")
    slog.system_start(config_summary={
        "embassy": YOUR_EMBASSY,
        "period_start": PRIOD_START,
        "period_end": PRIOD_END,
        "proxy_enabled": PROXY_ENABLED,
        "headless": HEADLESS
    })

    # Apply startup proxy selection based on strategy
    if PROXY_ENABLED and PROXY_MANAGER and PROXY_MANAGER.has_proxies:
        if PROXY_MANAGER.rotation_strategy == 'random':
            # Random strategy: randomly select a proxy at startup
            import random as rand_module
            PROXY_MANAGER.current_index = rand_module.randint(0, len(PROXY_MANAGER.proxies) - 1)
            proxy = PROXY_MANAGER.get_proxy()
            print(f"[PROXY] Random strategy: selected proxy {PROXY_MANAGER.current_index + 1}/{len(PROXY_MANAGER.proxies)}")
        # round_robin and on_ban: start from proxy1 (index 0), no action needed

    init_driver(PROXY_MANAGER if PROXY_ENABLED else None)

    # Log proxy configuration if enabled
    if PROXY_ENABLED and PROXY_MANAGER:
        slog.proxy_loaded(PROXY_MANAGER.total_count, PROXY_MANAGER.rotation_strategy)

    slog.session_start()

    # Startup notification
    startup_msg = f"Session started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n"
    startup_msg += f"Monitoring for dates between {PRIOD_START} and {PRIOD_END}."
    send_notification("SCHEDULER STARTED", startup_msg)

    t0 = time.time()
    Req_count = 0
    network_retry_count = 0
    consecutive_empty_count = 0  # Track consecutive empty responses for graduated ban detection

    # Load last notified earliest date from file (persists across restarts)
    EARLIEST_DATE_FILE = os.path.join("logs", ".last_earliest_date")
    last_notified_earliest_date = None
    if os.path.exists(EARLIEST_DATE_FILE):
        try:
            with open(EARLIEST_DATE_FILE, "r") as f:
                last_notified_earliest_date = f.read().strip() or None
        except Exception:
            pass

    try:
        start_process()

        while True:
            Req_count += 1
            slog.set_request_count(Req_count)

            # Heartbeat notification every 20 requests
            if Req_count % 20 == 0:
                running_mins = (time.time() - t0) / minute
                slog.heartbeat(Req_count, running_mins)
                send_notification("HEARTBEAT", f"Still running. {Req_count} checks. {running_mins:.0f} min.")

            try:
                dates = get_date_with_retry()

                if not isinstance(dates, list):
                    raise ValueError(f"Unexpected response type: {type(dates)} - {dates}")

                network_retry_count = 0 # Reset on success

                if not dates:
                    # Empty response - use graduated ban detection
                    consecutive_empty_count += 1

                    result = handle_empty_response(
                        consecutive_count=consecutive_empty_count,
                        cooldown_config=BAN_COOLDOWNS
                    )

                    if result['action'] == 'exit':
                        # Before exiting, try rotating proxy if available (all strategies rotate on ban)
                        if PROXY_ENABLED and PROXY_MANAGER and PROXY_MANAGER.has_proxies:
                            if rotate_proxy_and_restart():
                                slog.info(LogCategory.PROXY, "Rotated proxy after ban detection, restarting session")
                                consecutive_empty_count = 0  # Reset counter with new proxy
                                start_process()
                                continue
                        cleanup_and_exit(EXIT_BAN)
                    else:
                        # Sleep for graduated cooldown, then continue
                        time.sleep(result['duration'])
                        continue

                # Got valid dates - reset consecutive empty counter
                consecutive_empty_count = 0
                earliest = dates[0].get('date') if isinstance(dates[0], dict) else dates[0]
                slog.dates_found(dates, earliest)
                
                date = get_available_date(dates)
                if date:
                    slog.reschedule_start(date)
                    send_notification("Rescheduling Started", date)

                    # Fast retry logic for reschedule
                    max_reschedule_retries = 3
                    res = None
                    for attempt in range(max_reschedule_retries):
                        try:
                            slog.reschedule_attempt(date, attempt + 1, max_reschedule_retries)
                            res = reschedule(date)
                            break
                        except Exception as e:
                            slog.reschedule_exception(date, e, attempt + 1, max_reschedule_retries)

                            if attempt < max_reschedule_retries - 1:
                                # Immediate session recovery
                                slog.relogin_attempt(attempt + 1, max_reschedule_retries)
                                try:
                                    start_process()
                                    time.sleep(2)
                                    continue
                                except Exception as login_err:
                                    slog.login_failed(login_err, attempt + 1, max_reschedule_retries)

                            res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]

                    if res is None:
                        res = ["FAIL", "Unknown error during rescheduling"]

                    send_notification(res[0], res[1])

                    if res[0] == "SUCCESS":
                        # Extract time from message if possible
                        slog.reschedule_success(date, res[1].split()[-1] if res[1] else "")
                        cleanup_and_exit(EXIT_WORK_LIMIT)
                    elif res[0] == "NO_SLOTS":
                        slog.slot_taken(date)
                    else:
                        slog.reschedule_failed(date, res[1])
                        time.sleep(30)
                else:
                    # Dates available but not in target range - only notify if date moved EARLIER
                    # Skip notification if date moved later (slots taken - not interesting)
                    earliest = dates[0].get('date') if isinstance(dates[0], dict) else dates[0]
                    should_notify = (last_notified_earliest_date is None or earliest < last_notified_earliest_date)
                    if should_notify:
                        last_notified_earliest_date = earliest
                        # Persist to file so it survives restarts
                        try:
                            with open(EARLIEST_DATE_FILE, "w") as f:
                                f.write(earliest)
                        except Exception:
                            pass
                        dates_msg = f"{len(dates)} dates available. Earliest: {earliest}. Not in your target range ({PRIOD_START} to {PRIOD_END})."
                        send_notification("DATES AVAILABLE", dates_msg)

                # Time Checks
                t1 = time.time()
                total_time = t1 - t0
                running_minutes = total_time/minute

                if total_time > WORK_LIMIT_TIME * hour:
                    slog.work_limit_reached(running_minutes)
                    send_notification("WORK LIMIT", f"{WORK_LIMIT_TIME}h limit reached. Restarting immediately.")
                    cleanup_and_exit(EXIT_WORK_LIMIT)

                # Randomized Wait
                RETRY_WAIT_TIME = random.uniform(RETRY_TIME_L_BOUND, RETRY_TIME_U_BOUND)
                time.sleep(RETRY_WAIT_TIME)
                
            except Exception as e:
                # Network or API errors
                network_retry_count += 1
                slog.network_error("main_loop", e, network_retry_count, 3)
                if network_retry_count >= 3:
                     slog.error(LogCategory.NETWORK, "Max network retries exceeded", error=e)
                     # Try rotating proxy before giving up
                     if PROXY_ENABLED and PROXY_MANAGER and PROXY_MANAGER.has_proxies:
                         if rotate_proxy_and_restart():
                             slog.info(LogCategory.PROXY, "Rotated proxy after network errors, restarting session")
                             network_retry_count = 0  # Reset counter with new proxy
                             consecutive_empty_count = 0
                             start_process()
                             continue
                     # No proxy available or rotation failed, exit
                     send_notification("NETWORK ERROR", "Max retries exceeded. Script exiting. Will restart in 5 minutes.")
                     cleanup_and_exit(EXIT_NETWORK)
                time.sleep(60) # Short sleep before loop retry

    except Exception as e:
        slog.error(LogCategory.SYSTEM, f"Top level exception: {e}", error=e)
        send_notification("NETWORK ERROR", f"Top level exception: {e}. Script exiting. Will restart in 5 minutes.")
        cleanup_and_exit(EXIT_NETWORK)
