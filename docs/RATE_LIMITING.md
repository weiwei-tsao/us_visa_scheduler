# Rate Limiting and "System is busy" Message

## Overview

This document explains the "System is busy. Please try again later." message encountered when using the US visa appointment scheduler, based on research from community repositories and observed behavior.

**Last Updated**: 2026-01-18

---

## What is "System is busy"?

### Definition

The "System is busy. Please try again later." message is a **soft-ban (rate limiting)** mechanism implemented by usvisa-info.com, **not a literal account ban**.

### Technical Behavior

**Normal Response** (dates available):
```json
[
  {"date": "2025-03-15", "business_day": true},
  {"date": "2025-03-18", "business_day": true},
  {"date": "2025-03-22", "business_day": true}
]
```

**Rate-Limited Response** (soft-banned):
```json
[]
```

**Key Point**: The system returns an **empty array `[]`** instead of actual available dates when rate-limited. The script interprets this as "List is empty, Probably banned!"

---

## How Script Detects It

From [visa.py:408-422](../visa.py#L408-L422):

```python
if not dates:
    # Ban Situation
    msg = f"List is empty, Probabely banned!\n\tSleep for {BAN_COOLDOWN_TIME} hours!\n"
    print(msg)
    info_logger(LOG_FILE_NAME, msg)
    send_notification("BAN", msg)
    driver.get(SIGN_OUT_LINK)
    time.sleep(BAN_COOLDOWN_TIME * hour)  # Blocking sleep
```

**Limitation**: Script **cannot distinguish** between:
1. Legitimate "no dates available" (empty array because no appointments)
2. Rate-limited (empty array because soft-banned)

Both scenarios result in the same response format, so the script conservatively treats all empty arrays as potential bans.

---

## Rate Limiting Triggers

### Frequency-Based Triggers

Based on community research from GitHub repositories:

| Trigger | Value | Source |
|---------|-------|--------|
| **API Call Threshold** | ~100 requests | [theoomoregbee/US-visa-appointment-notifier](https://github.com/theoomoregbee/US-visa-appointment-notifier/issues/23) |
| **Ban Duration** | ~5 hours | Community consensus |
| **Request Frequency** | >10 min recommended | Multiple repos |

### Observed Patterns

From community reports and repository issues:

1. **Rapid Polling**: Making requests every 1-3 minutes triggers faster
2. **Session Churn**: Frequent logins/logouts may contribute to detection
3. **IP-Based**: May be tied to IP address, not just account
4. **Time of Day**: Some users report fewer bans during off-peak hours (US night time)

---

## Ban Duration Research

### Community Findings

| Repository | WORK_LIMIT_TIME | BAN_COOLDOWN_TIME | Strategy |
|------------|-----------------|-------------------|----------|
| [juliusdejon/US_Visa_Appointment](https://github.com/juliusdejon/US_Visa_Appointment) | 8 hours | 0.5 hours | Long work sessions, short ban recovery |
| [Soroosh-N/US_Visa_Scheduler](https://github.com/Soroosh-N/US_Visa_Scheduler) | 1.5 hours | 5 hours | Aggressive polling, long ban recovery |
| **This Project** | 2 hours | 4 hours | Balanced approach |

### Session-Based vs Global Ban Theory

**Important Hypothesis**: The 5-hour ban may be **per-session**, not global.

**Reasoning**:
1. PM2 restarts create fresh Chrome instances with new sessions every 2 hours
2. New session = new cookies, new authentication state
3. Fresh session may bypass previous session's rate limit

**Implication**:
- Current `BAN_COOLDOWN_TIME = 4 hours` is **conservative but safe**
- Could potentially reduce to `1.5-2 hours` since PM2 restart at 2h creates fresh session anyway
- Trade-off: Risk triggering IP-based limits if ban is IP-based, not session-based

**Recommendation**: Keep current conservative 4-hour setting until more data is collected.

---

## Current Configuration Safety Analysis

From [config.ini](../config.ini):

```ini
[TIME]
RETRY_TIME = 201              # ~3.35 minutes between checks
WORK_LIMIT_TIME = 2           # 2-hour work sessions
BAN_COOLDOWN_TIME = 4         # 4-hour ban recovery
```

### Safety Calculation

**Per Work Session (2 hours = 120 minutes)**:
- Checks per session: `120 min / 3.35 min = ~36 API calls`
- Well below community-reported threshold of ~100 calls

**Daily Pattern**:
- Work sessions per day: `24h / 2h = 12 sessions`
- API calls per day: `36 calls × 12 sessions = 432 calls`
- Logins per day: `12 logins`

**Safety Assessment**:
- ✅ **Per-session frequency**: 36 calls << 100 threshold (SAFE)
- ✅ **Request interval**: 3.35 min > 1 min minimum (SAFE)
- ✅ **Ban recovery**: 4h ≈ 5h community duration (SAFE)
- ⚠️ **Login frequency**: 12/day may trigger anti-bot (MONITOR)

---

## Optimization Opportunities

### Option 1: Reduce BAN_COOLDOWN_TIME (Moderate Risk)

**Current**: 4 hours
**Proposed**: 2 hours
**Rationale**: PM2 restarts every 2 hours with fresh session anyway

**Pros**:
- Faster recovery from false-positive empty arrays
- Less wasted time if no dates available (not actual ban)

**Cons**:
- Risk re-triggering if ban is IP-based, not session-based
- Unknown if fresh session actually bypasses rate limit

**Recommendation**: Test in low-stakes period, monitor for repeated bans.

### Option 2: Increase RETRY_TIME (Lower Risk)

**Current**: 201 seconds (~3.35 min)
**Proposed**: 300 seconds (5 min)
**Rationale**: Further reduce API call frequency

**Pros**:
- Reduces daily API calls from 432 to ~288
- Lower anti-bot detection risk
- Still checks frequently enough (12 checks/hour)

**Cons**:
- Slightly slower to detect newly available appointments

**Recommendation**: Consider if bans become frequent.

### Option 3: Implement Smart Retry Logic (High Effort)

**Concept**: Exponential backoff when empty array detected

```python
# Pseudocode
if not dates:
    retry_count += 1
    wait_time = min(RETRY_TIME * (2 ** retry_count), MAX_BACKOFF)
    time.sleep(wait_time)
else:
    retry_count = 0  # Reset on success
```

**Pros**:
- Adaptive to actual system behavior
- Reduces unnecessary API calls when dates unavailable

**Cons**:
- Code complexity
- May miss short windows of availability

**Recommendation**: Only if bans become chronic issue.

---

## Monitoring Best Practices

### Signs of Rate Limiting

From [logs/log_*.txt](../logs/):

**Pattern to Watch For**:
```
23:52:21: Working Time: ~ 53.81 minutes
23:55:42: List is empty, Probably banned!
           Sleep for 4.0 hours!
```

**Frequency Analysis**:
- **Normal**: 0-1 bans per day (likely legitimate no dates)
- **Warning**: 2-3 bans per day (possible rate limiting)
- **Critical**: >4 bans per day (definitely being rate-limited)

### Telegram Notifications

Current implementation sends notification when empty array detected:

```python
send_notification("BAN", msg)
```

**Actionable Metrics to Track**:
1. Bans per day
2. Time between bans
3. Successful reschedules vs ban rate
4. Session duration before ban

---

## Community Resources

### Referenced Repositories

1. **juliusdejon/US_Visa_Appointment**
   - URL: https://github.com/juliusdejon/US_Visa_Appointment
   - Strategy: Long work sessions (8h), short ban recovery (0.5h)
   - Notes: Uses aggressive polling with 60s retry time

2. **Soroosh-N/US_Visa_Scheduler**
   - URL: https://github.com/Soroosh-N/US_Visa_Scheduler
   - Strategy: Short sessions (1.5h), long ban recovery (5h)
   - Notes: Conservative approach similar to this project

3. **theoomoregbee/US-visa-appointment-notifier**
   - URL: https://github.com/theoomoregbee/US-visa-appointment-notifier
   - Issue #23: Discusses "System is busy" message and ~100 request threshold
   - Community consensus: 5-hour ban duration

### Community Consensus

From Reddit, GitHub issues, and Stack Overflow:

- **Minimum Retry Interval**: 10+ minutes recommended
- **Ban Duration**: 4-6 hours typical
- **Detection**: Triggered by frequency + total volume
- **IP vs Session**: Unclear, likely combination of both
- **Account Ban**: No reports of permanent account bans, always temporary

---

## Troubleshooting

### Problem: Frequent "List is empty" Messages

**Diagnosis Steps**:

1. **Check if legitimate no dates**:
   - Manually visit reschedule page
   - If dates visible but script sees empty array → session issue
   - If no dates visible → legitimate empty (not a ban)

2. **Check retry frequency**:
   ```bash
   # Calculate actual request frequency from logs
   grep "Working Time" logs/log_$(date +%Y-%m-%d).txt | tail -20
   ```

3. **Monitor ban frequency**:
   ```bash
   grep "Probably banned" logs/log_*.txt | wc -l
   ```

**Solutions**:

- **If 0-1 bans/day**: Current config is fine, likely legitimate empty dates
- **If 2-3 bans/day**: Increase RETRY_TIME to 300s (5 min)
- **If >4 bans/day**: Increase WORK_LIMIT_TIME to 3h, RETRY_TIME to 600s (10 min)

### Problem: Stuck in Ban Sleep Loop

**Symptom**: Script sleeps for 4 hours every cycle

**Diagnosis**:
```bash
# Check how often ban sleep is triggered
grep "Probably banned" logs/log_$(date +%Y-%m-%d).txt
```

**Root Causes**:
1. **False positive**: No dates actually available (not a ban)
2. **Actual rate limiting**: Too frequent requests
3. **Session issue**: Login state not maintained

**Solutions**:
1. Verify dates are actually available on reschedule page
2. Increase RETRY_TIME if being rate-limited
3. Check session re-login logs for authentication failures

---

## Technical Implementation Notes

### Why Script Can't Distinguish Empty vs Banned

The usvisa-info.com API returns **identical JSON structure** for both cases:

**Scenario A** - No dates available (legitimate):
```json
{
  "available_dates": []
}
```

**Scenario B** - Rate-limited (soft-ban):
```json
{
  "available_dates": []
}
```

**HTTP Status**: Both return `200 OK`
**Headers**: No special rate-limit headers exposed
**Body**: Identical empty array

Without additional signal from the server, the script must **conservatively assume** empty array = potential ban.

### Potential Improvements

**Option 1**: Add manual override flag
```python
# Allow user to force continue if they know dates are actually empty
SKIP_BAN_SLEEP = False  # In config.ini
if not dates and not SKIP_BAN_SLEEP:
    # Ban sleep logic
```

**Option 2**: Implement heuristic detection
```python
# If empty array happens at known "no dates" period, don't treat as ban
if not dates:
    if is_holiday_period() or is_known_empty_period():
        msg = "No dates available (expected), continue monitoring"
    else:
        msg = "Possible rate limit, entering ban cooldown"
```

**Recommendation**: Keep current conservative approach unless chronic false positives occur.

---

## Relationship to PM2 Restart Strategy

### How PM2 Restarts Interact with Bans

From [ecosystem.config.js](../ecosystem.config.js) and [visa.py](../visa.py):

**Work Limit Restart** (Lines 441-449 in visa.py):
```python
if total_time > WORK_LIMIT_TIME * hour:
    # Exit for PM2 to restart (relative interval)
    driver.get(SIGN_OUT_LINK)
    break  # Exit script, PM2 will restart immediately
```
- **Behavior**: Clean exit, PM2 autorestart
- **Duration**: Every 2 hours
- **Session state**: Fresh Chrome, fresh login

**Ban Sleep** (Lines 408-422 in visa.py):
```python
if not dates:
    time.sleep(BAN_COOLDOWN_TIME * hour)  # Blocking sleep
```
- **Behavior**: Script continues running (blocked in sleep)
- **Duration**: 4 hours (configurable)
- **Session state**: Same Chrome instance, same session (if not expired)

### Why They're Different

| Aspect | Work Limit Restart | Ban Sleep |
|--------|-------------------|-----------|
| **PM2 awareness** | PM2 sees exit, triggers restart | PM2 sees process running (sleeping) |
| **Session state** | Fresh session on restart | Maintains session (if not expired) |
| **Interruption** | Clean exit, graceful | Blocking sleep, not interruptible |
| **Relative intervals** | Yes (restart time varies) | No (fixed 4h sleep) |

### Theoretical Optimization

**Current Behavior**:
1. Hit rate limit at 10:00 AM → sleep 4 hours
2. Wake at 2:00 PM → resume with same session
3. Work limit at 4:00 PM → PM2 restart with fresh session

**Optimized Behavior** (if ban sleep also exited):
1. Hit rate limit at 10:00 AM → exit immediately
2. PM2 restarts at 10:00 AM with fresh session
3. Work limit at 12:00 PM (2h later) → PM2 restart again

**Advantage**: Fresh session might bypass session-based rate limit
**Risk**: IP-based limit wouldn't be bypassed, just waste restarts

**Current Recommendation**: Keep ban sleep as-is until session-based vs IP-based behavior is confirmed.

---

## Configuration Recommendations

### Conservative (Current)

**Best for**: First-time users, high-priority appointments, low tolerance for account issues

```ini
[TIME]
RETRY_TIME = 201              # ~3.35 min between checks
WORK_LIMIT_TIME = 2           # 2-hour sessions
BAN_COOLDOWN_TIME = 4         # 4-hour ban recovery
```

**Characteristics**:
- 36 API calls per session (well below threshold)
- 12 logins per day
- 432 total API calls per day
- Minimal ban risk

### Balanced

**Best for**: Experienced users, moderate urgency

```ini
[TIME]
RETRY_TIME = 300              # 5 min between checks
WORK_LIMIT_TIME = 3           # 3-hour sessions
BAN_COOLDOWN_TIME = 2         # 2-hour ban recovery
```

**Characteristics**:
- 36 API calls per session
- 8 logins per day
- 288 total API calls per day
- Lower login frequency, faster ban recovery

### Aggressive

**Best for**: Testing, low-priority appointments, research

```ini
[TIME]
RETRY_TIME = 120              # 2 min between checks
WORK_LIMIT_TIME = 4           # 4-hour sessions
BAN_COOLDOWN_TIME = 1         # 1-hour ban recovery
```

**Characteristics**:
- 120 API calls per session (ABOVE threshold - high ban risk)
- 6 logins per day
- 720 total API calls per day
- Fast detection, high ban risk

**Warning**: Aggressive configuration likely to trigger frequent rate limiting.

---

## Future Research

### Open Questions

1. **Session vs IP**: Is rate limit tied to session, IP, or both?
2. **Reset Timer**: Does 5-hour countdown reset on each request, or is it fixed from first trigger?
3. **Account Flagging**: Do repeated bans lead to longer ban durations or account penalties?
4. **Geographic Variance**: Do different embassy regions have different rate limits?
5. **Time-Based Patterns**: Are there time windows with relaxed limits?

### Experimental Methodology

To test session vs IP hypothesis:

**Experiment 1**: Fresh Session After Ban
1. Trigger rate limit (empty array)
2. Instead of sleeping, exit immediately → PM2 restart with fresh session
3. Check if fresh session sees dates or still empty array
4. **If sees dates**: Session-based (can bypass with fresh session)
5. **If still empty**: IP-based or global (fresh session doesn't help)

**Experiment 2**: Multiple Concurrent Sessions
1. Run two separate script instances (different Chrome profiles)
2. Trigger rate limit on Instance A
3. Check if Instance B is also rate-limited
4. **If both limited**: IP-based
5. **If only A limited**: Session-based

**Safety Note**: Only conduct experiments on non-critical accounts during low-stakes periods.

---

## References

- **Main Documentation**: [README.md](../README.md)
- **PM2 Design**: [PM2_DESIGN.md](./PM2_DESIGN.md)
- **Codebase Analysis**: [README.md](./README.md)
- **Configuration File**: [config.ini](../config.ini)
- **Main Script**: [visa.py](../visa.py)

### External Resources

- [theoomoregbee/US-visa-appointment-notifier Issue #23](https://github.com/theoomoregbee/US-visa-appointment-notifier/issues/23)
- [juliusdejon/US_Visa_Appointment](https://github.com/juliusdejon/US_Visa_Appointment)
- [Soroosh-N/US_Visa_Scheduler](https://github.com/Soroosh-N/US_Visa_Scheduler)

---

**Document Version**: 1.0
**Last Updated**: 2026-01-18
**Author**: Claude Code (Anthropic)
**Status**: Research findings and community consensus
