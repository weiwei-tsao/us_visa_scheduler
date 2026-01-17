# PM2 Monitoring Solution - Design Document

## Document Information

- **Created**: 2026-01-17
- **Purpose**: Design rationale for PM2 process management solution
- **Scope**: Automated monitoring and restart mechanism for visa scheduler

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Design Goals](#design-goals)
3. [Solution Overview](#solution-overview)
4. [Architecture](#architecture)
5. [Design Decisions](#design-decisions)
6. [Alternative Approaches Considered](#alternative-approaches-considered)
7. [Implementation Details](#implementation-details)
8. [Trade-offs](#trade-offs)
9. [Future Enhancements](#future-enhancements)

---

## Problem Statement

### Original Issues

The visa scheduler script encounters operational challenges when running unattended:

1. **Long Blocking Sleep Periods**
   - Ban cooldown: 5 hours when empty list detected
   - Work cooldown: 2.25 hours after work limit reached
   - Script becomes completely unresponsive during these periods
   - No way to interrupt or check status externally

2. **Manual Intervention Required**
   - Terminal must stay open throughout execution
   - Only way to restart: Kill process (Ctrl+C) and manually re-run
   - No automated recovery from crashes
   - Difficult to run 24/7 without supervision

3. **Lack of Visibility**
   - Can't distinguish between "healthy sleep" and "stuck/crashed"
   - No external monitoring capability
   - Log files only updated when script is active

### User Requirements

- Automated restart mechanism to prevent getting stuck in long sleeps
- Background execution without requiring open terminal
- Simple monitoring and manual restart capability
- Minimal code changes to existing working script
- Low maintenance overhead

---

## Design Goals

### Primary Goals

1. **Minimize Stuck Time**: Reduce maximum stuck time from 5 hours to acceptable threshold
2. **Zero Code Changes**: Avoid modifying working visa.py script
3. **Background Execution**: Enable running without terminal dependency
4. **Automatic Recovery**: Handle crashes and hangs without manual intervention
5. **Simple Operation**: Easy to start, stop, monitor, and restart

### Secondary Goals

1. **Memory Management**: Prevent Chrome memory leaks from accumulating
2. **Crash Loop Protection**: Avoid infinite restart cycles on persistent errors
3. **Log Organization**: Separate PM2 logs from application logs
4. **Persist Across Reboots**: Optional auto-start on system boot

---

## Solution Overview

### Chosen Approach: PM2-Only Time-Based Restarts

**Summary**: Use PM2 process manager with periodic cron-based restarts, without code modifications.

**Key Features**:
- Automatic restart every 4 hours via cron
- Immediate crash recovery via autorestart
- Memory limit monitoring (500MB threshold)
- Background daemon execution
- Built-in log management

**Why This Approach**:
- **Simplicity**: Single configuration file, no code changes
- **Proven Technology**: PM2 is mature, well-documented, widely used
- **Acceptable Trade-off**: 4-hour max stuck time vs 5-hour ban sleep
- **Low Maintenance**: Set-and-forget operation

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────┐
│                  PM2 Daemon                         │
│  (Node.js process manager running in background)    │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ Manages
                   ▼
┌─────────────────────────────────────────────────────┐
│           visa-scheduler Process                    │
│  • Script: visa.py                                  │
│  • Interpreter: python3                             │
│  • Cron: 0 */4 * * * (every 4 hours)               │
│  • Memory limit: 500MB                              │
│  • Autorestart: true                                │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ Controls
                   ▼
┌─────────────────────────────────────────────────────┐
│              Chrome Browser                         │
│  (Selenium WebDriver controlled)                    │
└─────────────────────────────────────────────────────┘
```

### Process Flow

```
User starts PM2
      ↓
PM2 spawns visa.py process
      ↓
visa.py opens Chrome and starts monitoring
      ↓
┌─────────────────────────────────────────┐
│  Script runs normally                   │
│  (polling, sleeping, rescheduling)      │
└─────────────────┬───────────────────────┘
                  │
                  │ Every 4 hours (cron)
                  │ OR on crash
                  │ OR on memory limit
                  ▼
PM2 kills visa.py process
      ↓
PM2 immediately spawns new visa.py
      ↓
New session re-logs in automatically
      ↓
Monitoring resumes
```

### Restart Triggers

| Trigger | Detection Method | Response Time | Type |
|---------|------------------|---------------|------|
| **Scheduled** | Cron: `0 */4 * * *` | Every 4 hours | Proactive |
| **Crash** | Process exit detected | <5 seconds | Reactive |
| **Memory limit** | Memory usage >500MB | Immediate | Proactive |
| **Manual** | User command: `pm2 restart` | Immediate | Manual |

---

## Design Decisions

### Decision 1: Restart Interval - 4 Hours

**Options Considered**:
- 2 hours (aggressive)
- 4 hours (balanced)
- 8 hours (conservative)
- No periodic restart

**Chosen**: 4 hours

**Rationale**:
- Ban cooldown is 5 hours → 4-hour restart ensures max wait of 4 hours (not 5)
- Long enough to allow productive work sessions
- Aligns with natural work periods (morning, afternoon, evening, night)
- Restarts at predictable times: 12am, 4am, 8am, 12pm, 4pm, 8pm
- Script's session recovery handles restarts gracefully

**Trade-off**: May interrupt legitimate operations, but script re-logs in automatically

---

### Decision 2: PM2-Only (No State Monitoring)

**Options Considered**:
1. **PM2 only** (time-based restarts)
2. **PM2 + Heartbeat monitoring** (state-aware restarts)
3. **PM2 + Manual override flag file** (user-triggered graceful restart)
4. **All three layers** (maximum robustness)

**Chosen**: PM2 only

**Rationale**:
- **Simplicity**: Zero code changes, single config file
- **Sufficient**: 4-hour window acceptable given user's use case
- **Maintainable**: No additional processes to manage
- **Reliable**: Time-based restarts are predictable and guaranteed
- **User preference**: User explicitly chose simple solution over complex monitoring

**What We Gave Up**:
- State-aware restart decisions (can't distinguish sleep from hang)
- Manual graceful restart via flag file
- Heartbeat logging for debugging

**Why It's Acceptable**:
- Script already has robust session recovery (`first_loop` flag)
- 4-hour forced restart is short enough for user's needs
- User confirmed ban sleep is only failure mode they encounter

---

### Decision 3: Separate Log Files

**Implementation**:
```javascript
error_file: './logs/pm2-error.log',
out_file: './logs/pm2-out.log',
```

**Rationale**:
- **Separation of concerns**: PM2 infrastructure logs separate from application logs
- **Debugging**: Can isolate PM2-level issues (crashes, restarts) from app-level issues
- **Retention**: Different lifecycle than daily app logs
- **Size management**: PM2 logs rotate independently

**Log Organization**:
```
./logs/
├── log_2026-01-17.txt    # App logs (created by visa.py)
├── pm2-out.log           # PM2 stdout (print statements)
└── pm2-error.log         # PM2 stderr (exceptions)
```

---

### Decision 4: Memory Limit - 500MB

**Chosen**: 500MB threshold

**Rationale**:
- Chrome typically uses 200-300MB for single tab
- 500MB threshold allows normal operation with safety margin
- Prevents runaway memory leaks from accumulating
- Forces periodic browser restart (fresh Chrome instance)

**Observation**: Chrome memory tends to grow over time due to:
- JavaScript heap retention
- WebDriver protocol overhead
- Multiple page navigations
- Cached resources

---

### Decision 5: Crash Loop Protection

**Configuration**:
```javascript
max_restarts: 10,
min_uptime: '60s'
```

**Rationale**:
- **Prevents infinite restart loops** if fundamental issue exists (bad credentials, network down)
- **60-second threshold**: Script must run for 60s to count as "successful start"
- **10 restart limit**: After 10 crashes within 60s window, PM2 stops trying
- **User notification**: Via Telegram if configured

**Example Scenario**:
```
12:00:00 - Script starts
12:00:05 - Crashes due to bad password
12:00:10 - Restart #1
12:00:15 - Crashes again
12:00:20 - Restart #2
...
12:00:55 - Restart #10
12:01:00 - PM2 gives up (10 crashes in <60s each)
```

User then checks `pm2 logs visa-scheduler --err` to diagnose root cause.

---

## Alternative Approaches Considered

### Approach A: Heartbeat Monitoring (Intelligent)

**How It Would Work**:
1. Script writes timestamp + state to `heartbeat.txt` every 30s
2. Separate monitor.py process checks heartbeat every 60s
3. If heartbeat stale (>5 min) or sleep exceeded, restart via PM2

**Advantages**:
- State-aware: Knows difference between sleep and hang
- Intelligent restart decisions
- Can detect stuck-in-sleep scenarios accurately
- Provides debugging information (state history)

**Disadvantages**:
- Requires code modifications to visa.py
- Extra process to manage (monitor.py)
- More complexity in failure modes
- Risk of false-positive restarts
- Monitor itself can crash

**Why Not Chosen**:
- User explicitly preferred no code changes
- Added complexity not justified for user's use case
- PM2-only approach achieves 80% of benefit with 20% of complexity

---

### Approach B: Manual Override Flag File

**How It Would Work**:
1. User creates `restart_now.flag` file
2. Script checks for flag every loop iteration
3. If flag exists: graceful shutdown, PM2 restarts
4. Flag deleted on startup to prevent restart loop

**Advantages**:
- User control over restart timing
- Graceful shutdown (clean browser close)
- Simple interface (just touch a file)
- Works even during long sleeps

**Disadvantages**:
- Requires code modifications
- Still need to wait for flag check (not immediate)
- Adds code complexity for edge case
- PM2 `restart` command already provides this

**Why Not Chosen**:
- `pm2 restart visa-scheduler` already provides manual restart
- Restart is fast enough (~5s) that graceful shutdown not critical
- Chrome cleanup happens in PM2 process termination

---

### Approach C: Systemd Service (Linux Native)

**How It Would Work**:
1. Create systemd service file for visa.py
2. Enable service: `systemctl enable visa-scheduler`
3. Systemd manages restarts and logging

**Advantages**:
- Native to Linux systems
- No Node.js dependency
- Boot-time auto-start built-in
- System-level integration

**Disadvantages**:
- Linux-only (user is on macOS)
- Less flexible restart policies than PM2
- Cron-based restart requires separate timer unit
- Less user-friendly commands than PM2
- No built-in monitoring dashboard

**Why Not Chosen**:
- User is on macOS (Darwin 22.6.0)
- PM2 works cross-platform
- PM2 has better DX (developer experience)

---

## Implementation Details

### File Structure

```
us_visa_scheduler/
├── ecosystem.config.js    # PM2 configuration (NEW)
├── status.sh              # Quick status script (NEW)
├── visa.py                # Main script (UNCHANGED)
├── config.ini             # User config (UNCHANGED)
├── logs/
│   ├── pm2-out.log       # PM2 stdout (NEW)
│   ├── pm2-error.log     # PM2 stderr (NEW)
│   └── log_*.txt         # App logs (UNCHANGED)
```

### PM2 Configuration Breakdown

```javascript
module.exports = {
  apps: [
    {
      // Process identification
      name: 'visa-scheduler',
      script: 'visa.py',
      interpreter: 'python3',

      // Restart policies
      cron_restart: '0 */4 * * *',  // Every 4h at minute 0
      max_memory_restart: '500M',    // Memory threshold
      autorestart: true,             // Restart on crash

      // Crash protection
      max_restarts: 10,              // Max restarts in min_uptime
      min_uptime: '60s',             // Success threshold

      // Logging
      error_file: './logs/pm2-error.log',
      out_file: './logs/pm2-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss'
    }
  ]
};
```

### Cron Syntax Explanation

`'0 */4 * * *'` = "At minute 0 of every 4th hour"

**Breakdown**:
- `0` - Minute (0 = top of the hour)
- `*/4` - Every 4th hour
- `*` - Every day of month
- `*` - Every month
- `*` - Every day of week

**Restart Times**:
- 00:00 (midnight)
- 04:00 (4am)
- 08:00 (8am)
- 12:00 (noon)
- 16:00 (4pm)
- 20:00 (8pm)

**Why minute 0**: Consistent, predictable restart times. Easy to correlate with logs.

---

### Status Script Breakdown

```bash
#!/bin/bash

# PM2 process status
pm2 status

# Last 5 app log entries
tail -n 5 logs/log_$(date +%Y-%m-%d).txt

# Chrome process count
ps aux | grep -i chrome | grep -v grep | wc -l

# PM2 restart counter
pm2 show visa-scheduler | grep "restarts"
```

**Purpose**: Single command to check system health

**Output Example**:
```
=== PM2 Status ===
┌─────┬──────────────┬─────┬─────┬──────┬────────┐
│ id  │ name         │ ↺   │ mem │ cpu  │ status │
├─────┼──────────────┼─────┼─────┼──────┼────────┤
│ 0   │ visa-sched.. │ 3   │ 285M│ 0%   │ online │
└─────┴──────────────┴─────┴─────┴──────┴────────┘

=== Last 5 App Log Entries ===
Request count: 42, Log time: 2026-01-17 14:30:15
Available dates: 2027-07-01, 2027-07-02
No available dates in target period
Working Time: ~ 45.2 minutes
Retry Wait Time: 201 seconds

=== Chrome Processes ===
Chrome instances: 8

=== Recent PM2 Restarts ===
restarts: 3
```

---

## Trade-offs

### What We Gained

| Benefit | Impact |
|---------|--------|
| **Max stuck time: 4h** | Down from 5h ban sleep |
| **Zero code changes** | No risk to working script |
| **Background execution** | No terminal dependency |
| **Crash recovery** | <5 second restart |
| **Memory protection** | Prevents leaks |
| **Simple monitoring** | `pm2 status` command |
| **Cross-platform** | Works on macOS/Linux/Windows |

### What We Gave Up

| Trade-off | Impact | Mitigation |
|-----------|--------|------------|
| **May interrupt operations** | Restart during active reschedule | Script re-logs in and retries |
| **Time-based (not state-aware)** | Can't distinguish sleep from hang | 4h window acceptable per user |
| **Node.js dependency** | Additional software required | One-time install |
| **Less intelligent** | No state logging | PM2 logs + app logs sufficient |

### Why Trade-offs Are Acceptable

1. **Script has robust recovery**: `first_loop` flag + automatic re-login
2. **4h window meets user needs**: Better than 5h ban sleep
3. **Operations are idempotent**: Interrupted reschedule just retries
4. **Node.js widely available**: Managed via Homebrew on macOS
5. **Logs provide sufficient debugging**: Combined PM2 + app logs

---

## Future Enhancements

### Phase 2: Heartbeat Monitoring (If Needed)

**When**: If 4-hour restarts prove too frequent or users request smarter restarts

**Changes**:
1. Add heartbeat writer to visa.py (minimal code change)
2. Create monitor.py to check heartbeat
3. Add monitor as second PM2 app
4. Adjust cron to 8-hour fallback

**Benefit**: State-aware restarts reduce unnecessary interruptions

---

### Phase 3: Metrics Collection (Optional)

**Purpose**: Understand script behavior over time

**Implementation**:
1. Parse daily logs for metrics
2. Track: ban frequency, reschedule success rate, date availability
3. Generate weekly summary reports
4. Alert on anomalies (increased ban rate, no dates for days)

**Use Case**: Optimize timing parameters, predict best checking times

---

### Phase 4: Multi-Instance Support (Advanced)

**Purpose**: Monitor multiple embassies simultaneously

**Implementation**:
1. Multiple PM2 apps in ecosystem.config.js
2. Separate config files: config-toronto.ini, config-vancouver.ini
3. Shared embassy.py, separate logs per instance
4. Consolidated monitoring dashboard

**Benefit**: One machine monitors all family members' appointments

---

### Phase 5: Cloud Deployment (Scaling)

**Purpose**: Run on cloud VM for 24/7 reliability

**Options**:
- AWS EC2 t2.micro (free tier)
- Google Cloud Platform f1-micro
- DigitalOcean $5/month droplet

**Changes**:
1. Headless Chrome (no display server)
2. Remote PM2 dashboard
3. Cloud logging integration
4. Static IP for consistent access

**Benefit**: Never worry about local machine uptime

---

## Maintenance

### Regular Tasks

**Daily**:
- Check `pm2 status` for restart count
- Review `./status.sh` output
- Monitor Telegram notifications

**Weekly**:
- Review `pm2 logs visa-scheduler --lines 1000`
- Check for excessive restarts (>20/day)
- Verify Chrome process count (should be 1-2 per session)

**Monthly**:
- Rotate large log files: `rm logs/pm2-*.log.old`
- Update PM2: `npm update -g pm2`
- Update Python dependencies: `pip install -r requirements.txt --upgrade`

### Troubleshooting

**High Restart Count**:
- Check error logs: `pm2 logs visa-scheduler --err`
- Verify credentials in config.ini
- Check network connectivity
- Review ban cooldown setting

**Memory Limit Hit Frequently**:
- Increase threshold: `max_memory_restart: '750M'`
- Check for Chrome leaks: `ps aux | grep chrome`
- Reduce work time: `WORK_LIMIT_TIME = 1.0`

**Cron Not Triggering**:
- Verify PM2 version: `pm2 --version` (need 5.0+)
- Check cron syntax: `pm2 show visa-scheduler | grep cron`
- Test with short interval: `'*/5 * * * *'` (every 5 min)

---

## Monitoring Best Practices

### Success Indicators

- Restart count: 6-8 per day (every 4h = 6/day)
- Memory usage: 200-400MB steady state
- Chrome processes: 8-12 per instance
- Uptime: >60s between restarts
- Status: "online" in `pm2 status`

### Warning Signs

- Restart count: >20/day (investigate crashes)
- Memory usage: Consistently hitting 500MB limit
- Chrome processes: >30 (zombie processes)
- Uptime: <60s (crash loop protection triggered)
- Status: "errored" or "stopped"

### Emergency Actions

**Script Won't Start**:
```bash
pm2 delete visa-scheduler
pm2 start ecosystem.config.js
pm2 logs visa-scheduler --err
```

**Too Many Chrome Processes**:
```bash
pkill -f chrome
pm2 restart visa-scheduler
```

**Return to Manual Mode**:
```bash
pm2 delete visa-scheduler
python3 visa.py
```

---

## Conclusion

### Design Summary

The PM2-only solution provides a **simple, reliable, and maintainable** monitoring system that solves the core problem (stuck in long sleeps) with minimal complexity and zero code changes.

**Key Design Principles Applied**:
1. **Simplicity over intelligence**: Time-based restarts sufficient
2. **Infrastructure over code**: Process manager handles lifecycle
3. **Proven tools**: PM2 is battle-tested
4. **Graceful degradation**: Script recovers from any restart
5. **User preferences**: No code changes, low maintenance

### Success Criteria Met

- ✅ Max stuck time: 4h (down from 5h)
- ✅ Zero code changes to visa.py
- ✅ Background execution without terminal
- ✅ Automatic crash recovery
- ✅ Simple monitoring and control
- ✅ Memory leak protection
- ✅ Low maintenance overhead

### When to Revisit

Consider adding heartbeat monitoring if:
- 4-hour restarts too frequent (>6/day seems excessive)
- Users want smarter restart logic
- Debugging requires state history
- False restart interruptions become problematic

For now, this PM2-only solution is the **right-sized** solution for the problem at hand.

---

## References

- **PM2 Documentation**: https://pm2.keymetrics.io/docs/usage/quick-start/
- **PM2 Cron Syntax**: https://pm2.keymetrics.io/docs/usage/restart-strategies/#cron-restart
- **Node.js Installation**: https://nodejs.org/en/download/
- **Project Main Documentation**: [../README.md](../README.md)
- **Codebase Analysis**: [./README.md](./README.md)

---

**Document Version**: 1.0
**Last Updated**: 2026-01-17
**Author**: Claude Code (Anthropic)
**Review Status**: Approved by User
