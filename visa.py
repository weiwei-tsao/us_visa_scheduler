import time
import json
import requests
import configparser
import os
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.common.by import By

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from embassy import *

config = configparser.ConfigParser()
config.read('config.ini')

# Personal Info:
# Account and current appointment info from https://ais.usvisa-info.com
USERNAME = config['PERSONAL_INFO']['USERNAME']
PASSWORD = config['PERSONAL_INFO']['PASSWORD']
# Find SCHEDULE_ID in re-schedule page link:
# https://ais.usvisa-info.com/en-am/niv/schedule/{SCHEDULE_ID}/appointment
SCHEDULE_ID = config['PERSONAL_INFO']['SCHEDULE_ID']
# Target Period:
PRIOD_START = config['PERSONAL_INFO']['PRIOD_START']
PRIOD_END = config['PERSONAL_INFO']['PRIOD_END']
# Embassy Section:
YOUR_EMBASSY = config['PERSONAL_INFO']['YOUR_EMBASSY'] 
EMBASSY = Embassies[YOUR_EMBASSY][0]
FACILITY_ID = Embassies[YOUR_EMBASSY][1]
REGEX_CONTINUE = Embassies[YOUR_EMBASSY][2]

# Notification:
# Get email notifications via https://sendgrid.com/ (Optional)
SENDGRID_API_KEY = config['NOTIFICATION']['SENDGRID_API_KEY']
SENDGRID_EMAIL_SENDER = config['NOTIFICATION']['SENDGRID_EMAIL_SENDER']

# Get push notifications via Telegram Bot (Optional)
TELEGRAM_BOT_TOKEN = config['NOTIFICATION'].get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = config['NOTIFICATION'].get('TELEGRAM_CHAT_ID', '')

# Time Section:
minute = 60
hour = 60 * minute
# Time between steps (interactions with forms)
STEP_TIME = 0.5
# Time between retries/checks for available dates (seconds)
RETRY_TIME = config['TIME'].getfloat('RETRY_TIME')
# Cooling down after WORK_LIMIT_TIME hours of work (Avoiding Ban)
WORK_LIMIT_TIME = config['TIME'].getfloat('WORK_LIMIT_TIME')
WORK_COOLDOWN_TIME = config['TIME'].getfloat('WORK_COOLDOWN_TIME')
# Temporary Banned (empty list): wait COOLDOWN_TIME hours
BAN_COOLDOWN_TIME = config['TIME'].getfloat('BAN_COOLDOWN_TIME')

# CHROMEDRIVER
# Details for the script to control Chrome
LOCAL_USE = config['CHROMEDRIVER'].getboolean('LOCAL_USE')
# Optional: HUB_ADDRESS is mandatory only when LOCAL_USE = False
HUB_ADDRESS = config['CHROMEDRIVER']['HUB_ADDRESS']

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

if LOCAL_USE:
    try:
        driver = webdriver.Chrome()
    except Exception as e:
        print(f"Failed to initialize Chrome with default driver: {e}")
        print("Trying with webdriver-manager...")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
else:
    driver = webdriver.Remote(command_executor=HUB_ADDRESS, options=webdriver.ChromeOptions())

def send_notification(title, msg):
    print(f"Sending notification!")

    # Send email via SendGrid
    if SENDGRID_API_KEY:
        message = Mail(from_email=SENDGRID_EMAIL_SENDER, to_emails=USERNAME, subject=title, html_content=msg)
        try:
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)
            print(f"Email sent - Status: {response.status_code}")
        except Exception as e:
            print(f"SendGrid error: {str(e)}")

    # Send message via Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        # Use HTML formatting for better readability
        def escape_html(text):
            # Escape HTML special characters
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        telegram_message = f"<b>{escape_html(title)}</b>\n\n{escape_html(msg)}"
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        telegram_data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": telegram_message,
            "parse_mode": "HTML"
        }
        try:
            response = requests.post(telegram_url, data=telegram_data)
            if response.status_code == 200:
                print("Telegram message sent successfully")
            else:
                print(f"Telegram error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Telegram error: {str(e)}")



def auto_action(label, find_by, el_type, action, value, sleep_time=0):
    print("\t"+ label +":", end="")
    # Find Element By
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
    # Do Action:
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
    # Bypass reCAPTCHA
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

    # Wait for page to load
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "authenticity_token")))

    headers = {
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
        "Referer": APPOINTMENT_URL,
        "Cookie": "_yatri_session=" + driver.get_cookie("_yatri_session")["value"]
    }

    # Build data dictionary with required fields
    data = {
        "appointments[consulate_appointment][facility_id]": FACILITY_ID,
        "appointments[consulate_appointment][date]": date,
        "appointments[consulate_appointment][time]": appointment_time,
    }

    # Add authenticity token (required)
    try:
        data["authenticity_token"] = driver.find_element(by=By.NAME, value='authenticity_token').get_attribute('value')
    except Exception as e:
        print(f"Warning: Could not find authenticity_token: {e}")
        return ["FAIL", f"Could not find authenticity token on reschedule page"]

    # Add optional fields (may or may not be present depending on Rails version)
    try:
        data["utf8"] = driver.find_element(by=By.NAME, value='utf8').get_attribute('value')
    except:
        pass  # utf8 field not present (Rails 6+), continue without it

    try:
        data["confirmed_limit_message"] = driver.find_element(by=By.NAME, value='confirmed_limit_message').get_attribute('value')
    except:
        pass  # confirmed_limit_message not present, continue without it

    try:
        data["use_consulate_appointment_capacity"] = driver.find_element(by=By.NAME, value='use_consulate_appointment_capacity').get_attribute('value')
    except:
        pass  # use_consulate_appointment_capacity not present, continue without it

    r = requests.post(APPOINTMENT_URL, headers=headers, data=data)
    if(r.text.find('Successfully Scheduled') != -1):
        title = "SUCCESS"
        msg = f"Rescheduled Successfully! {date} {appointment_time}"
    else:
        title = "FAIL"
        msg = f"Reschedule Failed!!! {date} {appointment_time}"
    return [title, msg]


def is_session_expired_error(error):
    """
    Detect if an error is related to session expiration.
    Common indicators:
    - JSON decode errors (empty response)
    - HTTP 401/403 errors
    - Specific error messages
    """
    error_str = str(error).lower()
    session_error_indicators = [
        'expecting value: line 1 column 1',  # Empty JSON response
        'json.decoder.jsondecodeerror',
        'empty response',  # Empty API response
        '401',  # Unauthorized
        '403',  # Forbidden
        'unauthorized',
        'session',
        'expired'
    ]
    return any(indicator in error_str for indicator in session_error_indicators)


def relogin():
    """
    Re-authenticate when session expires.
    Returns True if successful, False otherwise.
    """
    try:
        print("\n[SESSION] Session expired or invalid. Attempting to re-login...")
        log_file = os.path.join("logs", "log_" + str(datetime.now().date()) + ".txt")
        info_logger(log_file, "[SESSION] Session expired. Re-authenticating...")

        # Sign out first to clear old session
        try:
            driver.get(SIGN_OUT_LINK)
            time.sleep(STEP_TIME)
        except:
            pass  # Ignore errors if already signed out

        # Re-login
        start_process()
        print("[SESSION] Re-login successful!\n")
        info_logger(log_file, "[SESSION] Re-login successful!")
        return True
    except Exception as e:
        print(f"[SESSION] Re-login failed: {str(e)}")
        log_file = os.path.join("logs", "log_" + str(datetime.now().date()) + ".txt")
        info_logger(log_file, f"[SESSION] Re-login failed: {str(e)}")
        return False


def get_date():
    # Requesting to get the whole available dates
    session = driver.get_cookie("_yatri_session")["value"]
    script = JS_SCRIPT % (str(DATE_URL), session)
    content = driver.execute_script(script)
    return json.loads(content)


def get_date_with_retry(max_retries=2):
    """
    Get available dates with automatic session retry on failure.
    Detects session expiration and attempts re-login automatically.
    """
    for attempt in range(max_retries):
        try:
            session = driver.get_cookie("_yatri_session")["value"]
            script = JS_SCRIPT % (str(DATE_URL), session)
            content = driver.execute_script(script)

            # Check if content is empty or invalid
            if not content or content.strip() == '':
                raise ValueError("Empty response from API")

            return json.loads(content)
        except Exception as e:
            if is_session_expired_error(e) and attempt < max_retries - 1:
                # Try to re-login
                if relogin():
                    continue  # Retry the API call
                else:
                    raise  # Re-login failed, propagate error
            else:
                # Not a session error or last retry, propagate error
                raise


def get_time(date):
    time_url = TIME_URL % date
    session = driver.get_cookie("_yatri_session")["value"]
    script = JS_SCRIPT % (str(time_url), session)
    content = driver.execute_script(script)
    data = json.loads(content)
    time = data.get("available_times")[-1]
    print(f"Got time successfully! {date} {time}")
    return time


def get_time_with_retry(date, max_retries=2):
    """
    Get available time with automatic session retry on failure.
    Detects session expiration and attempts re-login automatically.
    """
    for attempt in range(max_retries):
        try:
            time_url = TIME_URL % date
            session = driver.get_cookie("_yatri_session")["value"]
            script = JS_SCRIPT % (str(time_url), session)
            content = driver.execute_script(script)

            # Check if content is empty or invalid
            if not content or content.strip() == '':
                raise ValueError("Empty response from API")

            data = json.loads(content)
            time = data.get("available_times")[-1]
            print(f"Got time successfully! {date} {time}")
            return time
        except Exception as e:
            if is_session_expired_error(e) and attempt < max_retries - 1:
                # Try to re-login
                if relogin():
                    continue  # Retry the API call
                else:
                    raise  # Re-login failed, propagate error
            else:
                # Not a session error or last retry, propagate error
                raise


def is_logged_in():
    content = driver.page_source
    if(content.find("error") != -1):
        return False
    return True


def get_available_date(dates):
    # Evaluation of different available dates
    def is_in_period(date, PSD, PED):
        new_date = datetime.strptime(date, "%Y-%m-%d")
        result = ( PED > new_date and new_date > PSD )
        # print(f'{new_date.date()} : {result}', end=", ")
        return result
    
    PED = datetime.strptime(PRIOD_END, "%Y-%m-%d")
    PSD = datetime.strptime(PRIOD_START, "%Y-%m-%d")
    for d in dates:
        date = d.get('date')
        if is_in_period(date, PSD, PED):
            return date
    print(f"\n\nNo available dates between ({PSD.date()}) and ({PED.date()})!")


def info_logger(file_path, log):
    # file_path: e.g. "log.txt"
    with open(file_path, "a") as file:
        file.write(str(datetime.now().time()) + ":\n" + log + "\n")


if __name__ == "__main__":
    first_loop = True
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    while 1:
        LOG_FILE_NAME = os.path.join("logs", "log_" + str(datetime.now().date()) + ".txt")
        if first_loop:
            # Add session divider to log file
            session_divider = "\n" + "=" * 80 + "\n"
            session_divider += f"NEW SESSION STARTED: {datetime.now()}\n"
            session_divider += "=" * 80 + "\n"
            info_logger(LOG_FILE_NAME, session_divider)

            t0 = time.time()
            total_time = 0
            Req_count = 0
            start_process()
            first_loop = False
        Req_count += 1
        try:
            msg = "-" * 60 + f"\nRequest count: {Req_count}, Log time: {datetime.today()}\n"
            print(msg)
            info_logger(LOG_FILE_NAME, msg)
            dates = get_date_with_retry()
            if not dates:
                # Ban Situation
                msg = f"List is empty, Probabely banned!\n\tSleep for {BAN_COOLDOWN_TIME} hours!\n"
                print(msg)
                info_logger(LOG_FILE_NAME, msg)
                send_notification("BAN", msg)
                driver.get(SIGN_OUT_LINK)
                time.sleep(BAN_COOLDOWN_TIME * hour)
                # Log session restart after ban
                restart_msg = "\n" + "=" * 80 + "\n"
                restart_msg += f"RESTARTING AFTER BAN COOLDOWN: {datetime.now()}\n"
                restart_msg += "=" * 80 + "\n"
                info_logger(LOG_FILE_NAME, restart_msg)
                first_loop = True
            else:
                # Print Available dates:
                msg = "Available dates:\n"
                for d in dates:
                    msg = msg + "%s" % (d.get('date')) + ", "
                print(msg)
                info_logger(LOG_FILE_NAME, msg)
                date = get_available_date(dates)
                if date:
                    # A good date to schedule for
                    send_notification("Rescheduling Started", date)
                    END_MSG_TITLE, msg = reschedule(date)
                    break
                RETRY_WAIT_TIME = RETRY_TIME
                t1 = time.time()
                total_time = t1 - t0
                msg = "\nWorking Time:  ~ {:.2f} minutes".format(total_time/minute)
                print(msg)
                info_logger(LOG_FILE_NAME, msg)
                if total_time > WORK_LIMIT_TIME * hour:
                    # Let program rest a little
                    send_notification("REST", f"Break-time after {WORK_LIMIT_TIME} hours | Repeated {Req_count} times")
                    driver.get(SIGN_OUT_LINK)
                    time.sleep(WORK_COOLDOWN_TIME * hour)
                    # Log session restart after work cooldown
                    restart_msg = "\n" + "=" * 80 + "\n"
                    restart_msg += f"RESTARTING AFTER WORK COOLDOWN: {datetime.now()}\n"
                    restart_msg += "=" * 80 + "\n"
                    info_logger(LOG_FILE_NAME, restart_msg)
                    first_loop = True
                else:
                    msg = "Retry Wait Time: "+ str(RETRY_WAIT_TIME)+ " seconds"
                    print(msg)
                    info_logger(LOG_FILE_NAME, msg)
                    time.sleep(RETRY_WAIT_TIME)
        except Exception as e:
            # Exception Occured
            msg = f"Break the loop after exception!\nError: {str(e)}\n"
            END_MSG_TITLE = "EXCEPTION"
            break

    # Cleanup after loop ends
    print(msg)
    info_logger(LOG_FILE_NAME, msg)
    send_notification(END_MSG_TITLE, msg)
    driver.get(SIGN_OUT_LINK)
    driver.stop_client()
    driver.quit()
