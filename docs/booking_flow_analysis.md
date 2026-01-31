# Auto Book Slots Workflow Analysis

## The Complete Booking Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: FETCH AVAILABLE DATES                                               │
│ Location: visa.py:748                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   dates = get_date_with_retry()                                             │
│                                                                             │
│   Flow:                                                                     │
│   1. Get session cookie: driver.get_cookie("_yatri_session")["value"]       │
│   2. Execute JS XMLHttpRequest to DATE_URL                                  │
│   3. Parse JSON response                                                    │
│                                                                             │
│   ⚠️ ISSUE #1: Line 656 - No null check on cookie                           │
│      If session cookie is missing, raises TypeError                         │
│      driver.get_cookie() returns None if cookie doesn't exist               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: FILTER DATES BY TARGET RANGE                                        │
│ Location: visa.py:791                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   date = get_available_date(dates)                                          │
│                                                                             │
│   Flow:                                                                     │
│   1. Parse PRIOD_START/PRIOD_END to datetime                                │
│   2. Loop through dates                                                     │
│   3. Check: PED > new_date and new_date > PSD (line 692)                    │
│   4. Return FIRST matching date                                             │
│                                                                             │
│   ⚠️ ISSUE #2: Line 692 - Strict inequality excludes boundaries             │
│      If PRIOD_START = "2026-06-01" and slot is on "2026-06-01"              │
│      → Date is EXCLUDED (won't book)                                        │
│      Should be: PED >= new_date >= PSD                                      │
│                                                                             │
│   ⚠️ ISSUE #3: Returns None silently if no match                            │
│      Only prints message, no explicit return value                          │
│      Line 706: just prints, doesn't return None explicitly                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: TRIGGER RESCHEDULE                                                  │
│ Location: visa.py:792-796                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   if date:                                                                  │
│       send_notification("Rescheduling Started", date)                       │
│       res = reschedule(date)                                                │
│       send_notification(res[0], res[1])                                     │
│       cleanup_and_exit(EXIT_WORK_LIMIT)  # Always exits!                    │
│                                                                             │
│   ⚠️ ISSUE #4: Line 796 - Exits regardless of success/failure               │
│      Both SUCCESS and FAIL result in cleanup_and_exit(0)                    │
│      If booking fails, script still exits                                   │
│      PM2 restarts, but no retry logic for failed booking                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: GET TIME SLOTS FOR DATE                                             │
│ Location: visa.py:602, 672-687                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   appointment_time = get_time_with_retry(date)                              │
│                                                                             │
│   Flow:                                                                     │
│   1. Build TIME_URL with date parameter                                     │
│   2. Fetch via JS XMLHttpRequest                                            │
│   3. Parse JSON: data = json.loads(content)                                 │
│   4. Return: data.get("available_times")[-1]                                │
│                                                                             │
│   🔴 CRITICAL ISSUE #5: Line 682 - No validation before [-1]                │
│                                                                             │
│      available_times = data.get("available_times")                          │
│      return available_times[-1]                                             │
│                                                                             │
│      Failure scenarios:                                                     │
│      • If available_times is None → TypeError: NoneType not subscriptable  │
│      • If available_times is []   → IndexError: list index out of range    │
│                                                                             │
│      This is the MOST CRITICAL BUG:                                         │
│      - Date is available (step 1 succeeded)                                 │
│      - But time slots could be empty/taken by time we fetch                 │
│      - Race condition: slot grabbed between date check and time fetch       │
│      - Script CRASHES at the exact moment of booking                        │
│                                                                             │
│   ⚠️ ISSUE #6: Takes LAST time slot [-1], not first [0]                     │
│      If times = ["09:00", "10:00", "15:00", "17:00"]                         │
│      Books 17:00 (latest) instead of 09:00 (earliest)                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: NAVIGATE TO APPOINTMENT PAGE                                        │
│ Location: visa.py:603-605                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   driver.get(APPOINTMENT_URL)                                               │
│   time.sleep(STEP_TIME)                                                     │
│   Wait(driver, 60).until(                                                   │
│       EC.presence_of_element_located((By.NAME, "authenticity_token"))       │
│   )                                                                         │
│                                                                             │
│   ⚠️ ISSUE #7: 60-second timeout may not be enough                          │
│      Under load, page could take longer                                     │
│      If timeout, raises TimeoutException - unhandled in reschedule()        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: BUILD FORM DATA                                                     │
│ Location: visa.py:607-628                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Required fields:                                                          │
│   - facility_id, date, time                                                 │
│   - authenticity_token (REQUIRED - has explicit error handling)             │
│                                                                             │
│   Optional fields (bare except):                                            │
│   - utf8                                                                    │
│   - confirmed_limit_message                                                 │
│   - use_consulate_appointment_capacity                                      │
│                                                                             │
│   ⚠️ ISSUE #8: Lines 623-628 - Bare except: pass                            │
│                                                                             │
│      try: data["utf8"] = driver.find_element(...)                           │
│      except: pass                                                           │
│                                                                             │
│      Problems:                                                              │
│      • Catches ALL exceptions (network, timeout, etc.)                      │
│      • Real errors are silently swallowed                                   │
│      • If required field extraction fails here, booking will fail           │
│        mysteriously                                                         │
│                                                                             │
│   ⚠️ ISSUE #9: Line 610 - Cookie access without null check                  │
│      driver.get_cookie("_yatri_session")["value"]                           │
│      Same issue as Step 1                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 7: SUBMIT BOOKING REQUEST                                              │
│ Location: visa.py:630                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   r = requests.post(APPOINTMENT_URL, headers=headers, data=data)            │
│                                                                             │
│   🔴 CRITICAL ISSUE #10: No timeout parameter                               │
│      If server hangs, request blocks FOREVER                                │
│      No way to recover                                                      │
│      Should be: requests.post(..., timeout=30)                              │
│                                                                             │
│   ⚠️ ISSUE #11: No HTTP status code check                                   │
│      Only checks response body text                                         │
│      HTTP 500/502/503 would go undetected                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 8: VERIFY BOOKING SUCCESS                                              │
│ Location: visa.py:631-634                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   if(r.text.find('Successfully Scheduled') != -1):                          │
│       return ["SUCCESS", f"Rescheduled Successfully! {date} {time}"]        │
│   else:                                                                     │
│       return ["FAIL", f"Reschedule Failed!!! {date} {time}"]                │
│                                                                             │
│   ⚠️ ISSUE #12: Fragile string matching                                     │
│      • Case-sensitive: "successfully scheduled" won't match                 │
│      • Exact phrase required                                                │
│      • If site changes wording, all bookings report as FAIL                 │
│      • Could have successful booking but wrong notification                 │
│                                                                             │
│   ⚠️ ISSUE #13: No response body logging on failure                         │
│      When booking fails, we don't know WHY                                  │
│      Should log r.text for debugging                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary: Issues by Severity

| Severity | Issue | Location | Impact |
|----------|-------|----------|--------|
| 🔴 **CRITICAL** | Empty time array crashes with IndexError | visa.py:682 | Booking fails at critical moment |
| 🔴 **CRITICAL** | No timeout on POST request | visa.py:630 | Script hangs indefinitely |
| 🟠 **HIGH** | Date boundary exclusion (strict `>`) | visa.py:692 | Valid dates on boundaries skipped |
| 🟠 **HIGH** | Always exits after booking attempt | visa.py:796 | No retry on failed booking |
| 🟠 **HIGH** | Takes LAST time slot, not first | visa.py:682 | Books inconvenient late times |
| 🟡 **MEDIUM** | No null check on session cookie | visa.py:656, visa.py:610 | TypeError if session lost |
| 🟡 **MEDIUM** | Bare `except: pass` clauses | visa.py:623-628 | Real errors hidden |
| 🟡 **MEDIUM** | Fragile string match for success | visa.py:631 | Wrong notification if wording changes |
| 🟢 **LOW** | No response logging on failure | visa.py:634 | Hard to debug failed bookings |

---

## Race Condition Scenario

The most dangerous scenario:

```
Time T+0:  get_date_with_retry() returns ["2026-06-15"]  ✓ Slot available
Time T+1:  get_available_date() finds date in range     ✓ Match found
Time T+2:  send_notification("Rescheduling Started")    ✓ User notified
Time T+3:  get_time_with_retry("2026-06-15") called
Time T+3:  Another user books the LAST slot for 2026-06-15
Time T+4:  API returns {"available_times": []}          ⚠️ Empty!
Time T+5:  data.get("available_times")[-1]              💥 IndexError!
Time T+6:  Script crashes, user sees "Rescheduling Started" but no result
```

This is a real race condition - the slot can be taken between date check and time fetch.
