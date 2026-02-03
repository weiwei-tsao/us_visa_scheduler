# Reschedule Retry Mechanism

## Problem Analysis (2026-02-02)

### Symptom
- Found available date 2026-02-05, sent Telegram notification
- Reschedule failed silently
- Date not recorded to `.last_earliest_date`
- 60 second wait before next attempt

### Root Cause

```
ChromeDriver exception during reschedule
    ↓
Caught by generic except block in main loop
    ↓
60 second sleep (network error handling)
    ↓
Slot taken by other users during wait
```

The generic exception handler treated ChromeDriver crashes the same as network errors, causing unnecessary delays during time-critical booking operations.

### Log Evidence

```
2026-02-02 04:03:20 - Found date: 2026-02-05
2026-02-02 04:03:20 - Telegram notification sent
2026-02-02 04:03:21 - Exception (ChromeDriver issue)
2026-02-02 04:04:21 - Next attempt (60s later - too slow)
```

## Solution

### Fast Retry for Reschedule

```python
# In main loop, when date found in target range:
max_reschedule_retries = 3
for attempt in range(max_reschedule_retries):
    try:
        slog.reschedule_attempt(date, attempt + 1, max_reschedule_retries)
        res = reschedule(date)
        break
    except Exception as e:
        slog.reschedule_exception(date, e, attempt + 1, max_reschedule_retries)

        if attempt < max_reschedule_retries - 1:
            # Immediate session recovery (not 60s wait)
            slog.relogin_attempt(attempt + 1, max_reschedule_retries)
            try:
                start_process()
                time.sleep(2)  # Brief stabilization
                continue
            except Exception as login_err:
                slog.login_failed(login_err, attempt + 1, max_reschedule_retries)

        res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]
```

### Key Changes

| Before | After |
|--------|-------|
| 60s wait on any error | 2s wait + immediate retry |
| 1 attempt | 3 attempts with session recovery |
| Generic error handling | Separate reschedule exception path |
| No retry logging | Structured retry attempt logging |

### Telegram Timeout Protection

```python
# Prevent notification blocking the booking flow
requests.post(telegram_url, data=telegram_data, timeout=5)
```

## Timeline Comparison

### Before Fix
```
04:03:20  Found date, notify
04:03:21  Exception
04:04:21  Retry (60s later) - slot gone
```

### After Fix
```
04:03:20  Found date, notify
04:03:21  Exception, attempt 1/3
04:03:23  Session recovery
04:03:25  Retry attempt 2/3
04:03:27  Success or attempt 3/3
```

Total recovery time: ~7 seconds vs 60 seconds

## Test Coverage

```bash
python -m pytest tests/test_reschedule_retry.py -v
```

23 test cases covering:
- Fast retry mechanism
- Session recovery on exception
- Telegram timeout handling
- Various exception types (WebDriver, Network, Session)

## Lessons Learned

1. **Time-critical operations need dedicated retry logic**
   - Don't reuse generic network error handlers
   - Keep retry delays minimal for booking scenarios

2. **External calls need timeouts**
   - Telegram notifications should not block booking
   - Set explicit timeout on all HTTP requests

3. **Structured logging enables diagnosis**
   - JSON logs with attempt counts pinpoint failures
   - Category-based filtering speeds up debugging

4. **Race conditions are inevitable in booking systems**
   - Multiple retries increase success probability
   - Log slot-taken events separately from errors

---

## Follow-up Optimization (2026-02-03)

After analyzing two reschedule failures (2026-02-24 and 2026-02-06), additional optimizations were implemented:

### Problem Identified

The original fix reduced retry interval from 60s to 2s, but **Selenium wait timeouts** were still 60s. This caused:
- Single reschedule timeout: 60s (too long)
- Single login timeout: 60s (too long)
- Total recovery time: 126s+ (slots taken by competitors)

### Additional Fixes

1. **Shortened Selenium Timeouts**
   ```python
   SELENIUM_WAIT_RESCHEDULE = 15  # Was 60s
   SELENIUM_WAIT_LOGIN = 20       # Was 60s
   ```

2. **Cloudflare Detection**
   ```python
   def detect_cloudflare_block():
       # Detects "Just a moment", "Access Denied", etc.
   ```

3. **Tiered Recovery Strategy**
   ```
   TimeoutException
        │
        ▼
   Check Cloudflare? ─Yes─→ Rotate Proxy (Level 3)
        │
        No
        ▼
   Page Refresh (Level 1)
        │
        ▼ Failed
   Full Re-login (Level 2)
        │
        ▼ Failed
   Rotate Proxy (Level 3)
   ```

### Expected Improvement

| Metric | Before | After |
|--------|--------|-------|
| Reschedule timeout | 60s | 15s |
| Login timeout | 60s | 20s |
| Worst-case 3 retries | 126s+ | ~67s |

See [reschedule-failure-analysis-2026-02-03.md](reschedule-failure-analysis-2026-02-03.md) for detailed analysis.
