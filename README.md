# visa_rescheduler

The visa_rescheduler is a bot for US VISA (usvisa-info.com) appointment rescheduling. This bot can help you reschedule your appointment to your desired time period.

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
RETRY_TIME = 60
; Cooling down after WORK_LIMIT_TIME hours of work (Avoiding Ban)(hours)
WORK_LIMIT_TIME = 8
WORK_COOLDOWN_TIME = 1
; Temporary Banned (empty list): wait COOLDOWN_TIME (hours)
BAN_COOLDOWN_TIME = 0.5

```

## Running

```
python3 visa.py
```
