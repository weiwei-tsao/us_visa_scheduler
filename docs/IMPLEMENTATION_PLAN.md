# Implementation Plan: Anti-Detection & Reliability Improvements

> **Branch**: `feature/anti-detection-implementation`
> **Base**: `docs/anti-detection-improvements`
> **Created**: 2026-01-31

---

## Overview

This plan implements the P0 and P1 improvements from `ANTI_DETECTION_AND_RELIABILITY_PLAN.md` in a phased approach with test coverage for each phase.

**Goals:**
1. Fix false positive ban detection (P0)
2. Enable configurable polling frequency (P0)
3. Add proxy rotation support (P1)

**Constraints:**
- Do not break existing working flows
- Each phase must be independently testable
- Maintain backward compatibility with current config.ini

---

## Phase 1: Improved Ban Detection

**Priority**: P0
**Estimated Scope**: Modify `visa.py`, add tests

### 1.1 Objectives

- Distinguish between real bans and false positives
- Implement graduated response (5min → 30min → 2hr → 4hr)
- Log HTTP status codes for analysis
- Add site status check before assuming ban

### 1.2 Changes Required

#### File: `visa.py`

| Function | Change |
|----------|--------|
| `get_date()` | Return HTTP status code along with dates |
| `get_date_with_retry()` | Track consecutive empty responses |
| Main loop | Implement graduated ban response |
| New function | `is_site_down()` - check external status |
| New function | `get_ban_cooldown()` - calculate wait time based on signals |

#### File: `config.ini`

Add new optional settings:
```ini
[BAN_DETECTION]
# Graduated cooldown times (in minutes)
COOLDOWN_FIRST_EMPTY = 5
COOLDOWN_SECOND_EMPTY = 30
COOLDOWN_THIRD_EMPTY = 120
COOLDOWN_HARD_BAN = 240

# Enable/disable site status check
CHECK_SITE_STATUS = True
```

### 1.3 Test Cases

#### Test File: `tests/test_ban_detection.py`

```
test_empty_array_first_time_short_cooldown()
    - Mock API returning empty array once
    - Verify cooldown is COOLDOWN_FIRST_EMPTY (5 min default)
    - Verify no notification sent

test_empty_array_consecutive_graduated_cooldown()
    - Mock API returning empty array 3 times consecutively
    - Verify cooldowns: 5min → 30min → 120min
    - Verify counter resets after successful response

test_http_403_immediate_long_cooldown()
    - Mock API returning HTTP 403
    - Verify cooldown is COOLDOWN_HARD_BAN (4 hours)
    - Verify ban notification sent

test_http_429_with_retry_after_header()
    - Mock API returning HTTP 429 with Retry-After: 300
    - Verify cooldown respects header value (300 seconds)

test_http_200_with_dates_resets_counter()
    - Mock sequence: empty → empty → dates → empty
    - Verify counter resets after receiving dates
    - Verify 4th response triggers first-level cooldown

test_site_status_check_down()
    - Mock site status check returning "down"
    - Verify short retry (5 min) instead of ban cooldown
    - Verify different log message

test_backward_compatibility()
    - Run with old config.ini (no BAN_DETECTION section)
    - Verify defaults are applied
    - Verify no crashes
```

### 1.4 Deliverables

- [ ] Modified `visa.py` with graduated ban detection
- [ ] Updated `config.ini.example` with new settings
- [ ] Test file `tests/test_ban_detection.py`
- [ ] Updated `docs/README.md` with new config options

### 1.5 Verification

```bash
# Run unit tests
python -m pytest tests/test_ban_detection.py -v

# Manual test: Run bot, observe graduated cooldown in logs
python visa.py

# Check logs for new format
grep "HTTP Status\|Cooldown\|Empty response" logs/log_*.txt
```

---

## Phase 2: Configurable Polling Frequency

**Priority**: P0
**Estimated Scope**: Config change + validation

### 2.1 Objectives

- Allow faster polling via config (no code change for basic use)
- Add validation for polling interval bounds
- Add warnings for aggressive settings
- Document recommended ranges

### 2.2 Changes Required

#### File: `visa.py`

| Function | Change |
|----------|--------|
| Config loading | Add validation for RETRY_TIME bounds |
| Startup | Warn if interval < 60 seconds without proxy |

#### File: `config.ini.example`

Update with recommended ranges:
```ini
[TIME]
# Polling interval bounds (seconds)
# Conservative: 111-300 (current default, ~18 checks/hour)
# Moderate: 60-120 (~40 checks/hour)
# Aggressive: 30-60 (~80 checks/hour, proxy recommended)
RETRY_TIME_L_BOUND = 60
RETRY_TIME_U_BOUND = 120
```

### 2.3 Test Cases

#### Test File: `tests/test_config_validation.py`

```
test_valid_retry_time_bounds()
    - Set RETRY_TIME_L_BOUND=60, RETRY_TIME_U_BOUND=120
    - Verify config loads successfully
    - Verify no warnings

test_invalid_bounds_lower_greater_than_upper()
    - Set RETRY_TIME_L_BOUND=300, RETRY_TIME_U_BOUND=100
    - Verify error raised at startup
    - Verify clear error message

test_aggressive_interval_warning()
    - Set RETRY_TIME_L_BOUND=10, RETRY_TIME_U_BOUND=30
    - Verify warning logged about ban risk
    - Verify bot continues (doesn't block)

test_zero_interval_rejected()
    - Set RETRY_TIME_L_BOUND=0
    - Verify error raised
    - Verify clear error message

test_negative_interval_rejected()
    - Set RETRY_TIME_L_BOUND=-10
    - Verify error raised

test_missing_config_uses_defaults()
    - Remove TIME section from config
    - Verify defaults (111, 300) are used
```

### 2.4 Deliverables

- [ ] Config validation in `visa.py`
- [ ] Warning system for aggressive settings
- [ ] Updated `config.ini.example` with documentation
- [ ] Test file `tests/test_config_validation.py`

### 2.5 Verification

```bash
# Run unit tests
python -m pytest tests/test_config_validation.py -v

# Test with moderate settings
# Edit config.ini: RETRY_TIME_L_BOUND=60, RETRY_TIME_U_BOUND=120
python visa.py
# Observe: ~40 checks/hour in logs

# Test validation
# Edit config.ini: RETRY_TIME_L_BOUND=300, RETRY_TIME_U_BOUND=100
python visa.py
# Expect: Error message and exit
```

---

## Phase 3: Proxy Rotation Support

**Priority**: P1
**Estimated Scope**: New module + config + integration

### 3.1 Objectives

- Add proxy configuration to config.ini
- Implement proxy rotation on session restart
- Implement proxy rotation on ban detection
- Add proxy health checking

### 3.2 Changes Required

#### New File: `proxy_manager.py`

```python
class ProxyManager:
    def __init__(self, proxy_list, rotation_strategy='round_robin')
    def get_proxy(self) -> dict
    def mark_failed(self, proxy)
    def rotate(self)
    def health_check(self, proxy) -> bool
```

#### File: `visa.py`

| Function | Change |
|----------|--------|
| `init_driver()` | Accept proxy parameter |
| Main loop | Rotate proxy on ban detection |
| Session restart | Get new proxy from manager |

#### File: `config.ini.example`

```ini
[PROXY]
# Enable proxy rotation
ENABLED = False

# Proxy list (one per line, format: protocol://user:pass@host:port)
# Or path to file containing proxies
PROXY_LIST =
    http://user:pass@proxy1.example.com:8080
    http://user:pass@proxy2.example.com:8080

# Rotation strategy: round_robin, random, on_ban
ROTATION_STRATEGY = round_robin

# Health check before using proxy
HEALTH_CHECK = True
```

### 3.3 Test Cases

#### Test File: `tests/test_proxy_manager.py`

```
test_proxy_manager_initialization()
    - Create manager with list of 3 proxies
    - Verify all proxies loaded
    - Verify initial proxy selected

test_round_robin_rotation()
    - Create manager with 3 proxies
    - Call rotate() 5 times
    - Verify sequence: 1 → 2 → 3 → 1 → 2

test_random_rotation()
    - Create manager with strategy='random'
    - Call rotate() 10 times
    - Verify proxies are selected (statistical check)

test_mark_failed_removes_proxy()
    - Create manager with 3 proxies
    - Mark one as failed
    - Verify only 2 proxies remain in rotation

test_all_proxies_failed()
    - Create manager with 2 proxies
    - Mark both as failed
    - Verify fallback to no proxy (or error)

test_health_check_pass()
    - Mock successful connection through proxy
    - Verify health_check() returns True

test_health_check_fail()
    - Mock failed connection through proxy
    - Verify health_check() returns False
    - Verify proxy marked as failed

test_proxy_format_parsing()
    - Test various proxy formats:
      - http://host:port
      - http://user:pass@host:port
      - socks5://host:port
    - Verify correct parsing

test_driver_with_proxy()
    - Initialize driver with proxy
    - Verify proxy is set in Chrome options
    - Verify driver starts successfully
```

#### Test File: `tests/test_proxy_integration.py`

```
test_proxy_rotation_on_session_restart()
    - Configure proxy rotation
    - Simulate session restart (WORK_LIMIT reached)
    - Verify new proxy selected

test_proxy_rotation_on_ban()
    - Configure proxy rotation with strategy='on_ban'
    - Simulate ban detection (HTTP 403)
    - Verify proxy rotated before cooldown

test_disabled_proxy_uses_direct()
    - Set PROXY.ENABLED = False
    - Verify driver uses direct connection
    - Verify no proxy-related errors
```

### 3.4 Deliverables

- [ ] New file `proxy_manager.py`
- [ ] Modified `visa.py` with proxy integration
- [ ] Updated `config.ini.example` with proxy settings
- [ ] Test files `tests/test_proxy_manager.py`, `tests/test_proxy_integration.py`
- [ ] Updated `docs/README.md` with proxy setup guide

### 3.5 Verification

```bash
# Run unit tests
python -m pytest tests/test_proxy_manager.py -v
python -m pytest tests/test_proxy_integration.py -v

# Manual test without proxy (backward compatibility)
# Ensure PROXY.ENABLED = False
python visa.py
# Verify: Works as before

# Manual test with proxy
# Set PROXY.ENABLED = True, add proxy list
python visa.py
# Verify: Logs show proxy in use
# Verify: Rotation on session restart
```

---

## Phase 4: Integration Testing & Documentation

**Priority**: P1
**Estimated Scope**: E2E tests, docs update

### 4.1 Objectives

- End-to-end integration tests
- Update all documentation
- Performance benchmarking

### 4.2 Test Cases

#### Test File: `tests/test_integration.py`

```
test_full_flow_no_proxy()
    - Run bot with moderate polling (60-120s)
    - Simulate: login → check dates → empty response → graduated cooldown
    - Verify all components work together

test_full_flow_with_proxy()
    - Run bot with proxy enabled
    - Simulate: login → check dates → ban → proxy rotation → retry
    - Verify proxy rotation triggers correctly

test_config_migration()
    - Start with old config.ini (no new sections)
    - Verify bot starts with defaults
    - Verify no errors

test_logging_format()
    - Run bot for simulated session
    - Verify logs contain HTTP status codes
    - Verify logs are parseable by analyze_logs.py
```

### 4.3 Documentation Updates

| File | Updates |
|------|---------|
| `README.md` (root) | Add proxy setup section, update config guide |
| `docs/README.md` | Update architecture diagram, add new components |
| `config.ini.example` | Full documentation of all new options |
| `CHANGELOG.md` | Document all changes (create if not exists) |

### 4.4 Deliverables

- [ ] Test file `tests/test_integration.py`
- [ ] Updated `README.md` (root)
- [ ] Updated `docs/README.md`
- [ ] New `CHANGELOG.md`
- [ ] Performance benchmark results

### 4.5 Verification

```bash
# Run all tests
python -m pytest tests/ -v

# Run integration tests specifically
python -m pytest tests/test_integration.py -v

# Verify documentation
# Manual review of all .md files
```

---

## Test Infrastructure Setup

Before implementing phases, set up test infrastructure:

### Create Test Directory Structure

```
tests/
├── __init__.py
├── conftest.py          # Shared fixtures
├── test_ban_detection.py
├── test_config_validation.py
├── test_proxy_manager.py
├── test_proxy_integration.py
├── test_integration.py
└── mocks/
    ├── __init__.py
    └── mock_responses.py  # Mock API responses
```

### Install Test Dependencies

Add to `requirements.txt`:
```
pytest>=7.0.0
pytest-mock>=3.10.0
responses>=0.23.0  # For mocking HTTP requests
```

### Shared Test Fixtures (`conftest.py`)

```python
import pytest
import tempfile
import configparser

@pytest.fixture
def temp_config():
    """Create temporary config.ini for testing"""
    config = configparser.ConfigParser()
    # ... default test config
    return config

@pytest.fixture
def mock_driver():
    """Mock Selenium WebDriver"""
    # ... mock implementation

@pytest.fixture
def mock_api_response():
    """Factory for mock API responses"""
    def _mock(status_code, dates=None, headers=None):
        # ... mock implementation
    return _mock
```

---

## Implementation Timeline

| Phase | Description | Dependencies |
|-------|-------------|--------------|
| Setup | Test infrastructure | None |
| Phase 1 | Ban detection | Setup |
| Phase 2 | Polling config | Phase 1 |
| Phase 3 | Proxy support | Phase 1 |
| Phase 4 | Integration | Phase 1, 2, 3 |

**Recommended Order:**
1. Setup test infrastructure
2. Phase 1 (Ban Detection) - highest impact
3. Phase 2 (Polling Config) - quick win
4. Phase 3 (Proxy Support) - enables aggressive polling
5. Phase 4 (Integration & Docs) - finalize

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing flow | Extensive backward compatibility tests |
| New bugs in production | Each phase independently deployable |
| Config migration issues | Default values for all new settings |
| Proxy reliability | Health check + fallback to direct |

---

## Rollback Plan

Each phase can be rolled back independently:

- **Phase 1**: Revert to `if not dates: sleep(4 hours)` logic
- **Phase 2**: Restore original RETRY_TIME values in config
- **Phase 3**: Set `PROXY.ENABLED = False`
- **Phase 4**: Documentation can remain (no code impact)

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| False positive bans/day | ~5 | < 1 |
| Checks/hour | ~18 | 40-80 |
| Hours lost to false bans | ~20/day | < 2/day |
| Earliest slot catchable | 14+ months | 6-12 months |

---

**Document Version**: 1.0
**Created**: 2026-01-31
**Author**: Claude Code
