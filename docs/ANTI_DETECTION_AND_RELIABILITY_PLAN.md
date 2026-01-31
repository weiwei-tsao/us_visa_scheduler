# Engineering Improvement Plan: US Visa Scheduler

> **Document Purpose**: Improve slot detection efficiency while avoiding bans.
> **Last Updated**: 2026-01-31

---

## Executive Summary: The Core Problem

**Your bot checks every 2-5 minutes. Earlier slots disappear within seconds.**

Log analysis (15 days of data) shows:
- Earliest date ever seen: **2027-03-08** (14 months out)
- Zero 2026 dates found
- 77 "ban" events (~5/day) - many likely false positives
- ~18 requests/hour vs. aggressive bots doing 300-700/hour
- One session ran 7+ hours with 431 requests without ban (Jan 25)

Competitive bots that catch 6-month slots poll **20-40x faster** than your current setup. The fundamental challenge is **speed vs. ban risk tradeoff**.

---

## Current Architecture Summary

Working features (do not break):
- `undetected-chromedriver` with 3-tier fallback
- Randomized retry intervals (111-300 seconds)
- Date range filtering (`PRIOD_START` / `PRIOD_END`)
- PM2 process management with session rotation
- 45-minute work sessions with automatic restart
- Telegram and SendGrid notifications

---

## 1. Polling Frequency Optimization

**Priority: P0 | This is the #1 factor limiting your success**

### Current Issue
- Check interval: 111-300 seconds (randomized)
- Actual rate: ~18 checks/hour
- Early slots appear and vanish in **seconds**, not minutes

### The Tradeoff
| Approach | Interval | Checks/Hour | Ban Risk | Slot Catch |
|----------|----------|-------------|----------|------------|
| Current | 111-300s | ~18 | Low | Very Low |
| Moderate | 30-60s | 60-120 | Medium | Low |
| Aggressive | 10-20s | 180-360 | High | Medium |
| With Proxies | 5-10s | 360-720 | Low* | High |

*With proxy rotation, ban risk stays low even at high frequency.

### Suggestion
**Phase 1 (No code change)**: Reduce `RETRY_TIME_L_BOUND` and `RETRY_TIME_U_BOUND` in config.ini:
- Conservative: 60-120 seconds (~40 checks/hour)
- Moderate: 30-60 seconds (~80 checks/hour)

**Phase 2 (Requires proxy)**: With proxy rotation enabled, can safely poll every 10-20 seconds.

### Risk Mitigation
- Monitor ban frequency after interval reduction
- If bans increase, back off or add proxy rotation first

---

## 2. Proxy Rotation

**Priority: P1 | Enables faster polling without ban risk**

### Current Issue
All requests from single IP. When banned:
- 4-hour cooldown = 4 hours of missed opportunities
- Same IP gets flagged again quickly
- No recovery path except waiting

### Suggestion
**Implement rotating residential proxies** to:
- Distribute requests across many IPs
- Rotate IP on ban detection (instant recovery)
- Enable aggressive polling (5-10 second intervals)

### Provider Options
| Provider | Type | Cost | Reliability |
|----------|------|------|-------------|
| Bright Data | Residential | $15-50/GB | High |
| IPRoyal | Residential | $7/GB | Medium |
| Oxylabs | Residential | $15/GB | High |
| Smartproxy | Datacenter | $10/month | Medium |

### Implementation Approach
- Add proxy config to `config.ini`
- Rotate proxy on each session restart (every 45 min)
- Optionally rotate on ban detection before cooldown
- Maintain proxy health check (skip dead proxies)

### Fingerprint Pairing Rule
When using proxies, ensure consistency:
| Proxy Location | Timezone | Language |
|----------------|----------|----------|
| Canada | America/Toronto | en-CA |
| US East | America/New_York | en-US |

Mismatched fingerprints (e.g., Canadian proxy with US timezone) are detectable.

---

## 3. Ban Detection Accuracy

**Priority: P0 | Critical - Current detection causes excessive downtime**

### Current Issue
```python
if not dates:  # Assumes ban → sleep 4 hours
```

This triggers on:
- Actual rate limiting (correct)
- Embassy has no dates (false positive)
- Temporary server glitch (false positive)
- Session expiration (false positive)
- Site maintenance (false positive)

77 "ban" events in 15 days - PM2 logs show many sessions making only 1 request before sleeping for hours. This is likely excessive false positives.

### Understanding the API Response

**Critical insight from community research:**

| Response | Meaning | What It Is NOT |
|----------|---------|----------------|
| Empty array `[]` | **Rate limit / Soft ban** | NOT "no appointments available" |
| Valid JSON with dates | Normal response | - |
| HTTP 403 | Hard ban (Cloudflare) | - |
| HTTP 429 | Rate limited | Check `Retry-After` header |
| Error 1015 page | Cloudflare rate limit | - |
| Connection timeout | Maintenance or network | NOT necessarily a ban |

**The empty array `[]` is a security/rate-limiting response, not a legitimate "no appointments" response.**

### How to Distinguish Ban vs. Maintenance vs. No Dates

| Check | How | Indicates |
|-------|-----|-----------|
| HTTP Status Code | Check response.status_code | 403/429 = definite ban, 200 = check further |
| Response Headers | Look for `cf-ray`, `Retry-After` | Cloudflare involvement, suggested wait time |
| Site Status | Check isitdownrightnow.com | Down for everyone = maintenance |
| Response Content | Check for "blocked" text | Explicit ban message |
| Consecutive Empty | Count empty responses | 1st may be glitch, 3rd+ likely ban |

### Suggested Detection Logic

```
1. Check HTTP status code FIRST
   - 403/429 → Definite ban → long cooldown (4 hours)
   - 5xx → Server error → short retry (5 min)
   - 200 → Check response content

2. If HTTP 200 + empty array:
   - 1st occurrence → short wait (5-10 min), retry
   - 2nd consecutive → medium wait (30 min)
   - 3rd consecutive → likely soft ban → wait 1-2 hours
   - Check site status to rule out maintenance

3. If HTTP 200 + Cloudflare challenge page:
   - Definite ban → rotate proxy or long cooldown

4. Log all HTTP status codes for analysis
```

### Community-Reported Patterns

From scheduler community discussions:
- Empty array typically appears after **48-100 requests**
- Soft ban reset takes **~5 hours** even if you stop immediately
- 60-second intervals give ~3 hours before hitting limit
- 5-minute intervals give ~4 hours before limit

---

## 4. Safe Login Flow

**Priority: P2 | Prevent failures from minor UI changes**

### Current Issue
Login flow uses hardcoded selectors. If site adds/removes optional UI elements (promotional banners, cookie notices), the bot may fail.

### Suggestion
**Graceful handling for non-critical elements**:
- Wrap optional element interactions in try/except
- Continue on `NoSuchElementException` for non-essential steps
- Log skipped elements for debugging

Elements to handle gracefully:
- Cookie consent banners
- Promotional pop-ups
- Optional checkboxes
- "Bounce arrow" animations

---

## 5. Network Timeouts & Retry Budget

**Priority: P2 | Prevent infinite hangs**

### Current Issue
`requests.post()` calls have no timeout. If the server hangs, the bot hangs indefinitely.

### Suggestion
Add explicit timeouts to all HTTP calls:
- Connect timeout: 10 seconds
- Read timeout: 30 seconds
- Retry budget: max 3 attempts with exponential backoff

Applies to:
- Reschedule POST request
- Telegram notification
- SendGrid notification

---

## 6. Deployment Reliability

**Priority: P2 | 24/7 operation**

### Current Issue
Running locally via PM2 depends on:
- Laptop staying awake
- No OS updates interrupting
- Stable network

### Suggestion
**Containerize with Docker** for VPS deployment ($5-10/month).

Benefits:
- 24/7 uptime on cloud infrastructure
- Reproducible environment
- Easy deployment to DigitalOcean, Linode, AWS Lightsail

Approach:
- Use `selenium/standalone-chrome` base image
- Map `config.ini` and `logs/` as volumes
- Use `docker-compose` for management

---

## 7. Configuration Validation

**Priority: P2 | Fail fast with clear errors**

### Current Issue
Invalid config causes runtime crashes:
- Bad date format
- Wrong embassy code
- Missing API keys silently disable notifications

### Suggestion
**Validate at startup**:
- Date format check (`YYYY-MM-DD`)
- Date logic (start < end, end > today)
- Embassy code exists in `embassy.py`
- Warn if notifications disabled

Also: Fix `config.ini.example` to be runnable out-of-box or fail with helpful message.

---

## 8. Browser Fingerprint Diversity

**Priority: P3 | Reduce behavioral detection**

### Current Issue
Each session uses identical fingerprint:
- Same viewport size
- Same timezone
- Same language

### Suggestion
**Randomize per session**:
- Viewport: 1920x1080, 1366x768, 1536x864
- Timezone: Match proxy location
- Language: en-US, en-CA, en-GB

---

## 9. Observability

**Priority: P3 | Know when something is wrong**

### Current Issue
Bot health only visible via manual log inspection.

### Suggestion
**Add monitoring**:
- Heartbeat file updated each loop
- Daily summary notification (requests, dates found, bans)
- External uptime check (Healthchecks.io)

---

## 10. Structured Logging

**Priority: P3 | Reliable log analysis**

### Current Issue
Plain text logs are fragile to parse. `analyze_logs.py` uses regex that can break.

### Suggestion
**Standardize log format** for key events:
- Use consistent delimiters
- Include machine-parseable fields (HTTP status, response size)
- Separate human-readable from structured data

---

## Priority Matrix

| # | Improvement | Impact | Effort | Priority |
|---|-------------|--------|--------|----------|
| 1 | Polling frequency reduction | **Critical** | Low | **P0** |
| 3 | Ban detection accuracy | **Critical** | Low | **P0** |
| 2 | Proxy rotation | **Critical** | Medium | **P1** |
| 4 | Safe login flow | Medium | Low | **P2** |
| 5 | Network timeouts | Medium | Low | **P2** |
| 6 | Docker deployment | Medium | Medium | **P2** |
| 7 | Config validation | Medium | Low | **P2** |
| 8 | Fingerprint diversity | Low | Medium | **P3** |
| 9 | Observability | Low | Low | **P3** |
| 10 | Structured logging | Low | Low | **P3** |

---

## Recommended Action Plan

### Immediate (This Week)
1. **Fix ban detection** - Don't sleep 4 hours on first empty array
   - Implement graduated response (5min → 30min → 2hr)
   - Log HTTP status codes to understand actual ban patterns
2. **Reduce polling interval** in config.ini to 60-120 seconds

### Short Term (1-2 Weeks)
3. **Add proxy support** - enables safe aggressive polling
4. **Add site status check** - verify if site is down before assuming ban

### Medium Term (2-4 Weeks)
5. **Move to VPS/Docker** - 24/7 reliability
6. **Add config validation** - fail fast on errors

---

## Key Insight

The current bot is **well-engineered for stealth but too slow for competition**. Toronto embassy slots within 6 months are grabbed by faster bots within seconds of appearing.

**Two critical issues:**
1. **Too slow**: Checking every 2-5 minutes when slots last seconds
2. **Too cautious**: Sleeping 4 hours on every empty array (many false positives)

The safest path forward:
1. **Fix ban detection first** - stop losing hours to false positives
2. **Then increase polling speed** - with proxy rotation for safety

---

## Log Analysis Summary

From `analyze_logs.py` (15 days of data):
```
Total Unique Dates Found: 112
Earliest Date: 2027-03-08 (14 months out)
Latest Date:   2027-11-30

By Month:
  2027-03: 2 dates   ← Rare early slots DO appear
  2027-04: 1 date
  2027-05: 3 dates
  2027-06: 11 dates
  2027-07+: Most dates
```

From `analyze_pm2.py` (268 sessions):
- Many sessions: 1 request → "Sleeping for 1.5h/4h/5h" (false positive bans)
- One session: 7+ hours, 431 requests, no ban (Jan 25)
- Proves aggressive polling is possible without real bans

---

## References & Sources

### Cloudflare Rate Limiting
- [Cloudflare Error 1015 Explanation](https://scrapfly.io/blog/posts/what-is-cloudflare-1015-error-and-how-to-fix-it) - "You are being rate limited" error details
- [Cloudflare 429 Documentation](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-429/) - Official rate limit response handling
- [Cloudflare Rate Limiting Parameters](https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/) - How WAF rate limiting works

### US Visa Site Specific
- [Blocked Access Discussion](https://community.cloudflare.com/t/blocked-access-to-us-visa-application-site/606572) - Community reports on visa site blocks
- [Error 1015 on US Embassy Site](https://community.cloudflare.com/t/error-1015-us-embassy-website/710225) - Specific visa site rate limiting
- [US Visa Site Block Solutions](https://ymgrad.com/article/ustraveldocs-blocked-error-solution) - Recovery approaches

### Scheduler Community Research
- [Empty Array Issue #23](https://github.com/theoomoregbee/US-visa-appointment-notifier/issues/23) - "After 100 API calls, API starts sending empty list"
- [Visa Scheduler Gist](https://gist.github.com/Svision/04202d93fb32d14f00ac746879820722) - Community findings on ban patterns, 5-hour reset time
- [US Appointment Scheduler Gist](https://gist.github.com/virgs/aad19b44440a053fd6410c40b1787e12) - Additional scheduler implementation notes

### Site Status Monitoring
- [Is US Visa Info Down?](https://www.isitdownrightnow.com/ais.usvisa-info.com.html) - Check if site is down for everyone

### Warning
From community discussions: One user reported having their **visa cancelled** for using automation scripts that violate the Terms of Service. Use at your own risk.

---

**Document Version**: 2.0
**Last Updated**: 2026-01-31
**Based On**: 15 days of log analysis + community research
