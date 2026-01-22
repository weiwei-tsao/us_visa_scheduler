# Architecture Update: Stealth & Safety (Jan 2026)

## Overview
This update shifts the bot's strategy from "brute force availability" to **"human-like stealth"**. The goal is to avoid detection, prevent permanent bans, and handle network instability gracefully.

## Key Changes

### 1. Randomized Retry Intervals (Stealth)
- **Old**: Fixed 63-second interval (Machine pattern).
- **New**: Randomized wait between **5 to 15 minutes**.
- **Reason**: Static intervals are a primary "bot fingerprint". Randomization mimics human checking patterns.

### 2. Wrapper Script Architecture (Safety)
- **Problem**: PM2 would restart the bot immediately after a ban detection or work limit, often creating infinite ban loops.
- **Solution**: Introduced `run_visa.sh` to manage exit codes.

| Exit Code | Meaning | Action Taken |
|:---:|:---|:---|
| **0** | Work Limit Reached | Restart immediately (New clean session) |
| **2** | **BAN DETECTED** | **Sleep 24 Hours** (Full cool-down) |
| **3** | Network Error | Sleep 5 Minutes (Wait for internet) |
| **Other**| Crash/Error | Sleep 1 Minute (Safety backoff) |

### 3. Reduced Work Limits
- **Old**: 1.5+ hours continuous work.
- **New**: **45 minutes** (~6-9 requests) per session.
- **Reason**: Keeps total requests per session well below the flagged threshold (~25 requests).

## Configuration Changes
The `config.ini` `[TIME]` section has been updated:

```ini
[TIME]
; Retry bounds in seconds (Randomized)
RETRY_TIME_L_BOUND = 300
RETRY_TIME_U_BOUND = 900
; Session duration in hours
WORK_LIMIT_TIME = 0.75
```

## How to Run
The entry point is now the wrapper script, managed by PM2.

```bash
# Start with PM2
pm2 start ecosystem.config.js
```
*Note: `ecosystem.config.js` has been updated to use `run_visa.sh` instead of `visa.py`.*
