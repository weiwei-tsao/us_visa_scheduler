# Bot Analysis & Stealth Implementation Summary

## 1. Workflow Analysis (`visa.py`)

The US Visa Scheduler bot uses a **Hybrid Selenium/Requests** approach:
1.  **Browser Initialization**: Launches Google Chrome via Selenium (now enhanced with `undetected-chromedriver`).
2.  **Authentication**: Performs standard login on `ais.usvisa-info.com` via browser automation.
3.  **Polling Strategy (Hybrid)**:
    -   Injects a synchronous `XMLHttpRequest` (JS) into the browser context to fetch `days.json` and `times.json`.
    -   This method is fast and reuses the browser's credentials without parsing full HTML.
4.  **Rescheduling Strategy**:
    -   When a slot is found, it switches to Python's `requests` library to send a POST request to the appointment endpoint.
    -   It mimics browser headers (User-Agent, Referer, Cookies) to appear legitimate.

### Analysis & Risk Assessment
*   **Strengths**: Fast polling (JSON API), effective session reuse.
*   **Previous Risks**: 
    *   **Fingerprinting**: Mismatch between Selenium's Chrome browser and Python's `requests` TLS signature.
    *   **Automation flags**: Standard Selenium `webdriver` property is easily detected by anti-bot systems.
*   **Mitigation**: The current random sleep intervals and work limits have successfully prevented bans recently.

## 2. Implemented Improvement: "Surgical Safety Patch"

To enhance safety without breaking the stable existing logic, we implemented a **Stealth Driver Upgrade**.

### Key Changes
1.  **Stealth Driver (`undetected-chromedriver`)**:
    *   Replaced the standard Selenium Chrome driver with `undetected-chromedriver`.
    *   **Benefit**: This patches the Chrome binary to remove standard automation flags (like `navigator.webdriver = true`), making the browser appear 99% human during the login phase.
    *   **Fallback**: Includes a robust fallback mechanism; if the stealth driver fails to launch, it automatically reverts to standard Selenium.

2.  **Headless Support**:
    *   Added `HEADLESS` option in `config.ini`.
    *   Allows running the bot on servers (VPS/EC2) without a graphical interface.
    *   *Note*: Headless mode generally has a higher detection risk than headed mode.

3.  **Minimal Invasion**:
    *   **Preserved**: The XHR polling logic (which is working well) was left untouched.
    *   **Preserved**: The `reschedule()` logic (complex form handling) was left untouched to avoid bugs.
    *   **Updated**: `config.ini.example` to include the new `[BEHAVIOR]` section.

## 3. Configuration

To use the new features, update your `config.ini`:

```ini
[BEHAVIOR]
; Headless mode: run without opening a visible browser window
HEADLESS = False

; Delay between steps (seconds) to mimic human speed
STEP_DELAY = 0.5
```
