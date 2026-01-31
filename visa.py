import time
import json
import requests
import configparser
import os
import sys
import random
from datetime import datetime

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

def handle_empty_response(consecutive_count, cooldown_config, log_file=None):
    """
    Handle empty response with graduated cooldown.

    Args:
        consecutive_count: Number of consecutive empty responses
        cooldown_config: Dict with cooldown values
        log_file: Optional log file path

    Returns:
        Dict with 'action' ('sleep' or 'exit') and 'duration' in seconds
    """
    cooldown = get_ban_cooldown(
        consecutive_empty_count=consecutive_count,
        http_status=200,  # Empty array comes with 200
        cooldown_config=cooldown_config
    )

    if cooldown == -1:
        # Too many consecutive empties, exit
        msg = f"[BAN] {consecutive_count} consecutive empty responses. Likely banned. Exiting."
        print(msg)
        if log_file:
            info_logger(log_file, msg)
        send_notification("BAN DETECTED", msg)
        return {'action': 'exit', 'duration': 0}

    # Log the graduated response
    msg = f"[BAN] Empty response #{consecutive_count}. Waiting {cooldown // 60} minutes before retry."
    print(msg)
    if log_file:
        info_logger(log_file, msg)

    # Only send notification on 3rd consecutive (warning before potential exit)
    if consecutive_count >= 3:
        send_notification("BAN WARNING", f"Multiple empty responses ({consecutive_count}). May be rate limited.")

    return {'action': 'sleep', 'duration': cooldown}

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

def init_driver():
    global driver
    if LOCAL_USE:
        # Try undetected-chromedriver first (Stealth Mode)
        if uc:
            try:
                options = webdriver.ChromeOptions()
                if HEADLESS:
                    options.add_argument('--headless')
                driver = uc.Chrome(options=options)
                print("Initialized undetected-chromedriver (Stealth Mode)")
                return
            except Exception as e:
                print(f"undetected-chromedriver failed: {e}")
                print("Falling back to standard Selenium...")
        
        # Fallback to standard Selenium
        try:
            options = webdriver.ChromeOptions()
            if HEADLESS:
                options.add_argument('--headless')
            driver = webdriver.Chrome(options=options)
        except Exception as e:
            print(f"Failed to initialize Chrome with default driver: {e}")
            print("Trying with webdriver-manager...")
            options = webdriver.ChromeOptions()
            if HEADLESS:
                options.add_argument('--headless')
            driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    else:
        options = webdriver.ChromeOptions()
        if HEADLESS:
            options.add_argument('--headless')
        driver = webdriver.Remote(command_executor=HUB_ADDRESS, options=options)


def send_notification(title, msg):
    print(f"Sending notification!")
    if SENDGRID_API_KEY:
        message = Mail(from_email=SENDGRID_EMAIL_SENDER, to_emails=USERNAME, subject=title, html_content=msg)
        try:
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)
            print(f"Email sent - Status: {response.status_code}")
        except Exception as e:
            print(f"SendGrid error: {str(e)}")

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
            requests.post(telegram_url, data=telegram_data)
        except Exception as e:
            print(f"Telegram error: {str(e)}")

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
    driver.get(SIGN_IN_LINK)
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "commit")))
    auto_action("Click bounce", "xpath", '//a[@class="down-arrow bounce"]', "click", "", STEP_TIME)
    auto_action("Email", "id", "user_email", "send", USERNAME, STEP_TIME)
    auto_action("Password", "id", "user_password", "send", PASSWORD, STEP_TIME)
    auto_action("Privacy", "class", "icheckbox", "click", "", STEP_TIME)
    auto_action("Enter Panel", "name", "commit", "click", "", STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(), '" + REGEX_CONTINUE + "')]")))
    print("\n\tlogin successful!\n")

def reschedule(date):
    appointment_time = get_time_with_retry(date)
    driver.get(APPOINTMENT_URL)
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "authenticity_token")))
    
    headers = {
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
        "Referer": APPOINTMENT_URL,
        "Cookie": "_yatri_session=" + driver.get_cookie("_yatri_session")["value"]
    }
    
    data = {
        "appointments[consulate_appointment][facility_id]": FACILITY_ID,
        "appointments[consulate_appointment][date]": date,
        "appointments[consulate_appointment][time]": appointment_time,
    }
    try:
        data["authenticity_token"] = driver.find_element(by=By.NAME, value='authenticity_token').get_attribute('value')
    except:
        return ["FAIL", f"Could not find authenticity token"]

    try: data["utf8"] = driver.find_element(by=By.NAME, value='utf8').get_attribute('value')
    except: pass
    try: data["confirmed_limit_message"] = driver.find_element(by=By.NAME, value='confirmed_limit_message').get_attribute('value')
    except: pass
    try: data["use_consulate_appointment_capacity"] = driver.find_element(by=By.NAME, value='use_consulate_appointment_capacity').get_attribute('value')
    except: pass

    r = requests.post(APPOINTMENT_URL, headers=headers, data=data)
    if(r.text.find('Successfully Scheduled') != -1):
        return ["SUCCESS", f"Rescheduled Successfully! {date} {appointment_time}"]
    else:
        return ["FAIL", f"Reschedule Failed!!! {date} {appointment_time}"]

def is_session_expired_error(error):
    error_str = str(error).lower()
    return any(x in error_str for x in ['expecting value', 'jsondecodeerror', 'empty response', '401', '403', 'unauthorized', 'session', 'expired'])

def relogin():
    try:
        print("\n[SESSION] Session expired. Re-authenticating...")
        try:
            driver.get(SIGN_OUT_LINK)
            time.sleep(STEP_TIME)
        except: pass
        start_process()
        return True
    except Exception as e:
        print(f"[SESSION] Re-login failed: {str(e)}")
        return False

def get_date_with_retry(max_retries=3):
    for attempt in range(max_retries):
        try:
            session = driver.get_cookie("_yatri_session")["value"]
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
                print(f"Network error (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(60) # Internal temporary network sleep
            else:
                raise

def get_time_with_retry(date, max_retries=3):
    for attempt in range(max_retries):
        try:
            time_url = TIME_URL % date
            session = driver.get_cookie("_yatri_session")["value"]
            script = JS_SCRIPT % (str(time_url), session)
            content = driver.execute_script(script)
            if not content or content.strip() == '':
                raise ValueError("Empty response from API")
            data = json.loads(content)
            return data.get("available_times")[-1]
        except Exception as e:
             if is_session_expired_error(e) and attempt < max_retries - 1:
                if relogin(): continue
                else: raise
             else: raise

def get_available_date(dates):
    def is_in_period(date, PSD, PED):
        new_date = datetime.strptime(date, "%Y-%m-%d")
        return ( PED > new_date and new_date > PSD )

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
    print(f"\n\nNo available dates between ({PSD.date()}) and ({PED.date()})!")

def info_logger(file_path, log):
    with open(file_path, "a") as file:
        file.write(str(datetime.now().time()) + ":\n" + log + "\n")

def cleanup_and_exit(exit_code):
    try:
        if driver:
            print("Closing Chrome Driver...")
            driver.quit()
    except:
        pass
    print(f"Exiting with code {exit_code}")
    sys.exit(exit_code)

if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    LOG_FILE_NAME = os.path.join("logs", "log_" + str(datetime.now().date()) + ".txt")
    
    init_driver()
    
    session_divider = "\n" + "=" * 80 + "\n"
    session_divider += f"NEW SESSION STARTED: {datetime.now()}\n"
    session_divider += "=" * 80 + "\n"
    info_logger(LOG_FILE_NAME, session_divider)
    
    t0 = time.time()
    Req_count = 0
    network_retry_count = 0
    consecutive_empty_count = 0  # Track consecutive empty responses for graduated ban detection

    try:
        start_process()

        while True:
            Req_count += 1
            msg = "-" * 60 + f"\nRequest count: {Req_count}, Log time: {datetime.today()}\n"
            print(msg)
            info_logger(LOG_FILE_NAME, msg)

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
                        cooldown_config=BAN_COOLDOWNS,
                        log_file=LOG_FILE_NAME
                    )

                    if result['action'] == 'exit':
                        cleanup_and_exit(EXIT_BAN)
                    else:
                        # Sleep for graduated cooldown, then continue
                        time.sleep(result['duration'])
                        continue

                # Got valid dates - reset consecutive empty counter
                consecutive_empty_count = 0
                
                msg = "Available dates:\n"
                for d in dates:
                    date_val = d.get('date') if isinstance(d, dict) else d
                    msg = msg + "%s" % date_val + ", "
                print(msg)
                info_logger(LOG_FILE_NAME, msg)
                
                date = get_available_date(dates)
                if date:
                    send_notification("Rescheduling Started", date)
                    res = reschedule(date)
                    send_notification(res[0], res[1])
                    cleanup_and_exit(EXIT_WORK_LIMIT) # Exit after successful schedule? Or continue? Usually stop.
                    
                # Time Checks
                t1 = time.time()
                total_time = t1 - t0
                running_minutes = total_time/minute
                msg = "\nWorking Time:  ~ {:.2f} minutes".format(running_minutes)
                print(msg)
                info_logger(LOG_FILE_NAME, msg)
                
                if total_time > WORK_LIMIT_TIME * hour:
                    msg = f"Work limit reached ({WORK_LIMIT_TIME}h). Exiting for restart."
                    print(msg)
                    info_logger(LOG_FILE_NAME, msg)
                    cleanup_and_exit(EXIT_WORK_LIMIT)
                
                # Randomized Wait
                RETRY_WAIT_TIME = random.uniform(RETRY_TIME_L_BOUND, RETRY_TIME_U_BOUND)
                msg = "Retry Wait Time: {:.1f} seconds".format(RETRY_WAIT_TIME)
                print(msg)
                info_logger(LOG_FILE_NAME, msg)
                time.sleep(RETRY_WAIT_TIME)
                
            except Exception as e:
                # Network or API errors
                print(f"Error in loop: {e}")
                network_retry_count += 1
                if network_retry_count >= 3:
                     msg = "Max network retries exceeded. Exiting with code 3."
                     print(msg)
                     info_logger(LOG_FILE_NAME, msg)
                     cleanup_and_exit(EXIT_NETWORK)
                time.sleep(60) # Short sleep before loop retry
                
    except Exception as e:
        print(f"Top level exception: {e}")
        cleanup_and_exit(EXIT_NETWORK)
