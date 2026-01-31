# Engineering Improvement Plan: US Visa Scheduler

> **Document Purpose**: Identify potential issues and improvement opportunities based on current codebase analysis.
> **Last Updated**: 2026-01-31

---

## Current Architecture Summary

The bot currently implements:
- `undetected-chromedriver` with 3-tier fallback
- Randomized retry intervals (111-300 seconds)
- Date range filtering (`PRIOD_START` / `PRIOD_END`)
- PM2 process management with session rotation
- 45-minute work sessions with automatic restart
- Telegram and SendGrid notifications

---

## 1. Deployment Reliability

### Current Issue
The bot runs locally via PM2, which depends on:
- Laptop staying awake and connected
- No OS updates or restarts interrupting execution
- Stable local network

### Suggestion
**Containerize with Docker** for VPS deployment ($5-10/month).

Benefits:
- 24/7 uptime on cloud infrastructure
- Reproducible environment across machines
- Easy deployment to any Docker-compatible host (DigitalOcean, Linode, AWS Lightsail)
- Isolation from host system updates

Considerations:
- Use `selenium/standalone-chrome` base image to avoid manual Chrome installation
- Map `config.ini` and `logs/` as volumes for persistence
- Consider `docker-compose` for easy management

---

## 2. IP-Based Rate Limiting

### Current Issue
All requests originate from a single IP address. If the IP gets flagged:
- Ban affects all future sessions
- 4-hour cooldown may not be sufficient
- No way to recover without manual IP change

### Suggestion
**Implement proxy rotation** to distribute requests across multiple IPs.

Options:
- Residential proxy services (Bright Data, Oxylabs, IPRoyal)
- Rotating datacenter proxies (cheaper but higher detection risk)
- VPN rotation (manual, less reliable)

Implementation approach:
- Rotate proxy on each new session (every 45 minutes)
- Or rotate on ban detection before cooldown
- Store proxy list in config, select randomly

Trade-offs:
- Cost: $20-50/month for quality residential proxies
- Complexity: Proxy authentication and health checking
- Reliability: Some proxies may be pre-flagged

---

## 3. Browser Fingerprint Diversity

### Current Issue
Each session uses identical browser fingerprint:
- Same viewport size (default)
- Same timezone
- Same language settings
- Same WebGL/Canvas fingerprint

Repeated identical fingerprints from same IP can trigger behavioral detection.

### Suggestion
**Randomize browser characteristics** per session.

Randomizable parameters:
- Viewport size (common resolutions: 1920x1080, 1366x768, 1536x864)
- Timezone (match with proxy location if using proxies)
- Language headers (`en-US`, `en-CA`, `en-GB`)
- Window position on screen

Lower priority (more complex):
- WebGL renderer spoofing
- Canvas noise injection
- Audio context fingerprint

---

## 4. Request Library Fingerprint Mismatch

### Current Issue
The bot uses two HTTP clients:
1. **Selenium/Chrome** for login and date polling (via JS injection)
2. **Python `requests`** library for the actual reschedule POST

These have different TLS fingerprints (JA3), which sophisticated WAFs can detect as anomalous behavior.

### Suggestion
**Unify request handling** through the browser.

Option A: Submit reschedule form via Selenium
- Use `driver.find_element()` and `.click()` for form submission
- Eliminates fingerprint mismatch entirely
- Trade-off: Slower, more DOM interaction code

Option B: Use `curl_cffi` or `tls-client`
- Python libraries that mimic browser TLS fingerprints
- Drop-in replacement for `requests`
- Trade-off: Additional dependency, may need maintenance

---

## 5. Ban Detection Accuracy

### Current Issue
Ban detection relies on empty date array response:
```
if not dates:  # Assumes ban
    sleep(4 hours)
```

This may produce false positives:
- Embassy genuinely has no available dates
- Temporary server issue
- Session expiration edge case

4-hour sleep on false positive = significant missed opportunity window.

### Suggestion
**Improve ban signal detection** with multiple indicators.

Better detection heuristics:
- Check HTTP status code (403/429 = definite ban)
- Check response headers for Cloudflare challenge tokens
- Check page content for CAPTCHA or block messages
- Track pattern: single empty response vs. repeated empty responses

Graduated response:
- 1st empty response: Short retry (5 min), refresh session
- 2nd consecutive: Medium retry (30 min)
- 3rd consecutive or explicit 403: Long cooldown (2-4 hours)

---

## 6. Session Cookie Extraction Timing

### Current Issue
Session cookie is extracted once after login and reused for all API calls within the session. If the cookie expires mid-session:
- API calls fail with auth errors
- Triggers re-login flow
- Re-login increases detection risk (unusual pattern)

### Suggestion
**Proactive session refresh** before expiration.

Approach:
- Track session start time
- Refresh session at ~30-35 minutes (before 45-min work limit)
- Or detect cookie expiration time from response headers
- Graceful re-auth without full browser restart

---

## 7. Notification Reliability

### Current Issue
Notifications are synchronous and fire-and-forget:
- If SendGrid/Telegram API is slow, delays the main loop
- If notification fails, no retry
- No confirmation that critical alerts were delivered

### Suggestion
**Async notifications with retry** for critical events.

For "slot found" and "reschedule success" events:
- Retry notification up to 3 times on failure
- Log notification delivery status
- Consider backup channel (if Telegram fails, try email)

Lower priority:
- Move to async/threading (adds complexity)
- Current blocking approach is acceptable for rare events

---

## 8. Observability and Monitoring

### Current Issue
Bot health is only visible via:
- Manual log file inspection
- PM2 status commands
- Notifications on specific events

No way to know if bot is "stuck" or running but ineffective.

### Suggestion
**Add health monitoring and metrics**.

Simple approach:
- Heartbeat file updated each loop iteration
- External cron job checks file age, alerts if stale
- Daily summary notification (requests made, dates found, errors)

Advanced approach:
- Prometheus metrics endpoint
- Grafana dashboard
- Uptime monitoring service (UptimeRobot, Healthchecks.io)

---

## 9. Configuration Validation

### Current Issue
`config.ini` is parsed at startup with minimal validation:
- Invalid date formats cause runtime crashes
- Missing API keys silently disable notifications
- Typos in embassy codes fail at runtime

### Suggestion
**Validate configuration at startup** with clear error messages.

Validations to add:
- Date format check (`PRIOD_START`, `PRIOD_END`)
- Date logic check (start < end, end > today)
- Embassy code exists in `embassy.py`
- Notification credentials format (API key length, chat ID format)
- Warn if notifications are disabled (missing keys)

---

## Priority Matrix

| Improvement | Impact | Effort | Priority |
|-------------|--------|--------|----------|
| Docker containerization | High | Medium | **P1** |
| Ban detection accuracy | High | Low | **P1** |
| Proxy rotation | High | Medium | **P2** |
| Config validation | Medium | Low | **P2** |
| Browser fingerprint diversity | Medium | Medium | **P3** |
| Request library unification | Medium | High | **P3** |
| Health monitoring | Low | Low | **P3** |
| Notification retry | Low | Low | **P4** |
| Session refresh optimization | Low | Medium | **P4** |

---

## Summary

The current implementation is solid with good anti-detection foundations. The highest-impact improvements are:

1. **Move to Docker/VPS** for reliability
2. **Improve ban detection** to reduce false positive downtime
3. **Add proxy rotation** for IP-level resilience

These three changes would significantly improve the bot's effectiveness and resilience without major architectural changes.
