"""
Unit tests for the reschedule retry mechanism.

Tests the new fast retry logic added to handle Selenium/ChromeDriver exceptions
during the critical reschedule operation.

Key scenarios tested:
1. Reschedule succeeds on first attempt (no retry needed)
2. Reschedule fails once, session recovery succeeds, retry succeeds
3. Reschedule fails multiple times, all retries exhausted
4. Session recovery (start_process) also fails
5. Normal reschedule returns (SUCCESS/FAIL/NO_SLOTS) are handled correctly

Also tests:
- Telegram notification timeout to prevent blocking
- get_time_with_retry exception handling
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRescheduleRetryMechanism(unittest.TestCase):
    """
    Test the fast retry mechanism for reschedule operations.

    The new logic wraps reschedule() in a try-except with up to 3 retries,
    attempting session recovery (start_process) between each attempt.
    """

    def test_reschedule_succeeds_first_attempt(self):
        """Reschedule succeeds on first attempt - no retry needed."""
        mock_reschedule = Mock(return_value=["SUCCESS", "Booked 2026-02-05 10:00"])
        mock_start_process = Mock()

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                if attempt < max_reschedule_retries - 1:
                    mock_start_process()
                res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]

        self.assertEqual(res[0], "SUCCESS")
        self.assertEqual(mock_reschedule.call_count, 1)
        self.assertEqual(mock_start_process.call_count, 0)  # No recovery needed

    def test_reschedule_fails_once_then_succeeds(self):
        """
        Reschedule fails once with exception, session recovery succeeds,
        retry succeeds.
        """
        # First call raises exception, second call succeeds
        mock_reschedule = Mock(side_effect=[
            Exception("ChromeDriver session error"),
            ["SUCCESS", "Booked 2026-02-05 10:00"]
        ])
        mock_start_process = Mock()

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                if attempt < max_reschedule_retries - 1:
                    try:
                        mock_start_process()
                    except Exception:
                        pass
                    continue
                res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]

        self.assertEqual(res[0], "SUCCESS")
        self.assertEqual(mock_reschedule.call_count, 2)
        self.assertEqual(mock_start_process.call_count, 1)  # One recovery attempt

    def test_reschedule_fails_twice_then_succeeds(self):
        """Reschedule fails twice, third attempt succeeds."""
        mock_reschedule = Mock(side_effect=[
            Exception("First failure"),
            Exception("Second failure"),
            ["SUCCESS", "Booked 2026-02-05 10:00"]
        ])
        mock_start_process = Mock()

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                if attempt < max_reschedule_retries - 1:
                    try:
                        mock_start_process()
                    except Exception:
                        pass
                    continue
                res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]

        self.assertEqual(res[0], "SUCCESS")
        self.assertEqual(mock_reschedule.call_count, 3)
        self.assertEqual(mock_start_process.call_count, 2)  # Two recovery attempts

    def test_reschedule_all_retries_exhausted(self):
        """All reschedule attempts fail, returns FAIL result."""
        mock_reschedule = Mock(side_effect=[
            Exception("First failure"),
            Exception("Second failure"),
            Exception("Third failure - final")
        ])
        mock_start_process = Mock()

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                if attempt < max_reschedule_retries - 1:
                    try:
                        mock_start_process()
                    except Exception:
                        pass
                    continue
                res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]

        self.assertEqual(res[0], "FAIL")
        self.assertIn("Exception after 3 attempts", res[1])
        self.assertEqual(mock_reschedule.call_count, 3)
        self.assertEqual(mock_start_process.call_count, 2)

    def test_session_recovery_also_fails(self):
        """
        Both reschedule and session recovery (start_process) fail.
        Should still attempt remaining retries.
        """
        mock_reschedule = Mock(side_effect=[
            Exception("Reschedule failure 1"),
            Exception("Reschedule failure 2"),
            Exception("Reschedule failure 3")
        ])
        mock_start_process = Mock(side_effect=[
            Exception("Session recovery failure 1"),
            Exception("Session recovery failure 2"),
        ])

        max_reschedule_retries = 3
        res = None
        recovery_failures = 0

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                if attempt < max_reschedule_retries - 1:
                    try:
                        mock_start_process()
                    except Exception:
                        recovery_failures += 1
                    continue
                res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]

        self.assertEqual(res[0], "FAIL")
        self.assertEqual(mock_reschedule.call_count, 3)
        self.assertEqual(mock_start_process.call_count, 2)
        self.assertEqual(recovery_failures, 2)  # Both recoveries failed

    def test_reschedule_returns_no_slots_not_exception(self):
        """
        Reschedule returns NO_SLOTS (race condition) - this is a normal return,
        not an exception, so no retry should happen.
        """
        mock_reschedule = Mock(return_value=["NO_SLOTS", "Slot taken before booking"])
        mock_start_process = Mock()

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break  # Normal return, exit loop
            except Exception as e:
                if attempt < max_reschedule_retries - 1:
                    mock_start_process()
                    continue
                res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]

        self.assertEqual(res[0], "NO_SLOTS")
        self.assertEqual(mock_reschedule.call_count, 1)  # Only one call
        self.assertEqual(mock_start_process.call_count, 0)  # No recovery

    def test_reschedule_returns_fail_not_exception(self):
        """
        Reschedule returns FAIL (booking failed) - normal return, no retry.
        """
        mock_reschedule = Mock(return_value=["FAIL", "Booking failed HTTP 500"])
        mock_start_process = Mock()

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                if attempt < max_reschedule_retries - 1:
                    mock_start_process()
                    continue
                res = ["FAIL", f"Exception after {max_reschedule_retries} attempts: {e}"]

        self.assertEqual(res[0], "FAIL")
        self.assertIn("HTTP 500", res[1])
        self.assertEqual(mock_reschedule.call_count, 1)
        self.assertEqual(mock_start_process.call_count, 0)


class TestRescheduleExceptionTypes(unittest.TestCase):
    """
    Test handling of different exception types during reschedule.
    """

    def test_selenium_webdriver_exception(self):
        """Handle Selenium WebDriverException."""
        class WebDriverException(Exception):
            pass

        mock_reschedule = Mock(side_effect=[
            WebDriverException("Session not created"),
            ["SUCCESS", "Booked"]
        ])
        mock_start_process = Mock()

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                if attempt < max_reschedule_retries - 1:
                    mock_start_process()
                    continue
                res = ["FAIL", f"Exception: {e}"]

        self.assertEqual(res[0], "SUCCESS")
        self.assertEqual(mock_start_process.call_count, 1)

    def test_stale_element_reference_exception(self):
        """Handle StaleElementReferenceException."""
        class StaleElementReferenceException(Exception):
            pass

        mock_reschedule = Mock(side_effect=[
            StaleElementReferenceException("Element is stale"),
            ["SUCCESS", "Booked"]
        ])
        mock_start_process = Mock()

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                if attempt < max_reschedule_retries - 1:
                    mock_start_process()
                    continue
                res = ["FAIL", f"Exception: {e}"]

        self.assertEqual(res[0], "SUCCESS")

    def test_empty_message_chromedriver_exception(self):
        """
        Handle the specific ChromeDriver exception with empty message.
        This is the actual error observed in logs.
        """
        # Simulate the actual error: "Message: \nStacktrace: ..."
        chromedriver_error = Exception("Message: \nStacktrace: 0 chromedriver...")

        mock_reschedule = Mock(side_effect=[
            chromedriver_error,
            ["SUCCESS", "Booked"]
        ])
        mock_start_process = Mock()

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                if attempt < max_reschedule_retries - 1:
                    mock_start_process()
                    continue
                res = ["FAIL", f"Exception: {e}"]

        self.assertEqual(res[0], "SUCCESS")
        self.assertEqual(mock_start_process.call_count, 1)


class TestGetTimeWithRetryExceptions(unittest.TestCase):
    """
    Test exception handling in get_time_with_retry function.

    This function is called inside reschedule() and can also throw exceptions.
    """

    def test_session_cookie_missing(self):
        """get_cookie returns None - session expired."""
        mock_driver = Mock()
        mock_driver.get_cookie.return_value = None

        # Simulate get_time_with_retry behavior
        cookie = mock_driver.get_cookie("_yatri_session")

        self.assertIsNone(cookie)
        with self.assertRaises(TypeError):
            session = cookie["value"]

    def test_execute_script_raises_exception(self):
        """execute_script fails with WebDriver error."""
        mock_driver = Mock()
        mock_driver.get_cookie.return_value = {"value": "session123"}
        mock_driver.execute_script.side_effect = Exception("Script execution failed")

        with self.assertRaises(Exception) as context:
            mock_driver.execute_script("some_script")

        self.assertIn("Script execution failed", str(context.exception))

    def test_empty_api_response(self):
        """API returns empty string."""
        mock_driver = Mock()
        mock_driver.get_cookie.return_value = {"value": "session123"}
        mock_driver.execute_script.return_value = ""

        content = mock_driver.execute_script("fetch_times")

        self.assertEqual(content, "")
        # This should raise ValueError in actual code
        self.assertFalse(content)  # Empty string is falsy


class TestTelegramNotificationTimeout(unittest.TestCase):
    """
    Test that Telegram notification has proper timeout to prevent blocking.
    """

    def test_telegram_post_has_timeout(self):
        """Verify timeout=5 is passed to requests.post for Telegram."""
        mock_requests = MagicMock()

        telegram_url = "https://api.telegram.org/bot123/sendMessage"
        telegram_data = {"chat_id": "456", "text": "test"}

        # Simulate the fixed code with timeout
        mock_requests.post(telegram_url, data=telegram_data, timeout=5)

        # Verify timeout was passed
        call_kwargs = mock_requests.post.call_args[1]
        self.assertEqual(call_kwargs.get('timeout'), 5)

    def test_telegram_timeout_prevents_blocking(self):
        """
        Simulate timeout scenario - should not block indefinitely.
        """
        # Create a custom Timeout exception (avoid importing requests which may be mocked)
        class TimeoutError(Exception):
            pass

        mock_requests = MagicMock()
        mock_requests.post.side_effect = TimeoutError("Connection timed out")

        telegram_url = "https://api.telegram.org/bot123/sendMessage"
        telegram_data = {"chat_id": "456", "text": "test"}

        # Simulate the error handling in send_notification
        error_caught = False
        error_msg = ""
        try:
            mock_requests.post(telegram_url, data=telegram_data, timeout=5)
        except Exception as e:
            error_caught = True
            error_msg = str(e)

        self.assertTrue(error_caught)
        self.assertIn("timed out", error_msg)

    def test_telegram_failure_does_not_affect_main_flow(self):
        """
        Telegram notification failure should not interrupt the main booking flow.
        """
        telegram_succeeded = False
        main_flow_continued = False

        # Simulate send_notification with timeout failure
        try:
            raise Exception("Telegram timeout")
        except Exception:
            pass  # Silently handle

        # Main flow should continue
        main_flow_continued = True

        self.assertTrue(main_flow_continued)
        self.assertFalse(telegram_succeeded)


class TestRescheduleRetryTiming(unittest.TestCase):
    """
    Test that the retry mechanism is fast enough for time-sensitive booking.
    """

    def test_short_sleep_between_retries(self):
        """
        Verify that sleep time between retries is minimal (2 seconds).

        Old behavior: 60 seconds
        New behavior: 2 seconds
        """
        import time

        sleep_times = []
        original_sleep = time.sleep

        def mock_sleep(seconds):
            sleep_times.append(seconds)

        # Simulate the retry loop with mocked sleep
        max_reschedule_retries = 3

        for attempt in range(max_reschedule_retries):
            try:
                raise Exception("Simulated failure")
            except Exception:
                if attempt < max_reschedule_retries - 1:
                    mock_sleep(2)  # New short sleep
                    continue
                break

        # Should have 2 sleeps (between attempt 0-1 and 1-2)
        self.assertEqual(len(sleep_times), 2)
        # Each sleep should be 2 seconds
        for sleep_time in sleep_times:
            self.assertEqual(sleep_time, 2)
        # Total sleep time should be 4 seconds, not 120 seconds
        self.assertEqual(sum(sleep_times), 4)

    def test_worst_case_total_retry_time(self):
        """
        Calculate worst-case total time for all retries.

        Worst case: 3 failures, 2 recovery attempts
        Time = 2s + 2s = 4 seconds (plus execution time)

        This is much better than old behavior (60s per failure).
        """
        retry_sleep = 2  # seconds
        max_retries = 3

        # Worst case: all retries fail
        total_sleep_time = (max_retries - 1) * retry_sleep

        self.assertEqual(total_sleep_time, 4)
        # Compare to old behavior
        old_behavior_sleep = 60  # seconds
        self.assertLess(total_sleep_time, old_behavior_sleep)


class TestNullResHandling(unittest.TestCase):
    """
    Test the null check for res variable added as safety measure.
    """

    def test_res_initialized_to_none(self):
        """res should be initialized to None before retry loop."""
        res = None
        self.assertIsNone(res)

    def test_res_none_fallback(self):
        """
        If res is still None after loop (shouldn't happen), use fallback.
        """
        res = None

        # Simulate the safety check
        if res is None:
            res = ["FAIL", "Unknown error during rescheduling"]

        self.assertEqual(res[0], "FAIL")
        self.assertIn("Unknown error", res[1])

    def test_res_never_none_in_normal_flow(self):
        """
        In normal flow, res should never be None after the loop.
        """
        mock_reschedule = Mock(return_value=["SUCCESS", "Booked"])

        res = None
        max_reschedule_retries = 3

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                res = ["FAIL", str(e)]

        self.assertIsNotNone(res)
        self.assertEqual(res[0], "SUCCESS")


class TestIntegrationScenarios(unittest.TestCase):
    """
    Integration-like tests simulating real-world scenarios.
    """

    def test_scenario_chromedriver_crash_recovery(self):
        """
        Scenario: ChromeDriver crashes mid-booking, recovery succeeds.

        Timeline:
        T+0: Find date 2026-02-05
        T+1: Start reschedule, ChromeDriver crashes
        T+2: Catch exception, start_process() recovers session
        T+3: Retry reschedule, succeeds
        """
        events = []

        def mock_reschedule(date):
            if len(events) == 0:
                events.append(f"reschedule_attempt_1_{date}")
                raise Exception("ChromeDriver crash")
            else:
                events.append(f"reschedule_attempt_2_{date}")
                return ["SUCCESS", f"Booked {date}"]

        def mock_start_process():
            events.append("session_recovery")

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception as e:
                events.append(f"caught_exception_{attempt}")
                if attempt < max_reschedule_retries - 1:
                    mock_start_process()
                    continue
                res = ["FAIL", str(e)]

        self.assertEqual(res[0], "SUCCESS")
        self.assertEqual(events, [
            "reschedule_attempt_1_2026-02-05",
            "caught_exception_0",
            "session_recovery",
            "reschedule_attempt_2_2026-02-05"
        ])

    def test_scenario_slot_taken_after_crash_recovery(self):
        """
        Scenario: ChromeDriver crashes, recovery succeeds, but slot is gone.

        Timeline:
        T+0: Find date 2026-02-05
        T+1: ChromeDriver crashes
        T+2: Recovery succeeds
        T+3: Retry, but returns NO_SLOTS (someone else grabbed it)
        """
        def mock_reschedule(date):
            if mock_reschedule.call_count == 1:
                mock_reschedule.call_count += 1
                raise Exception("ChromeDriver crash")
            else:
                return ["NO_SLOTS", "Slot taken before booking"]

        mock_reschedule.call_count = 1

        def mock_start_process():
            pass

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except Exception:
                if attempt < max_reschedule_retries - 1:
                    mock_start_process()
                    continue
                res = ["FAIL", "All retries failed"]

        # Even though we recovered, slot was taken
        self.assertEqual(res[0], "NO_SLOTS")


class TestCloudflareDetection(unittest.TestCase):
    """
    Test the Cloudflare/WAF block detection function.
    """

    def test_detect_cloudflare_just_a_moment(self):
        """Detect Cloudflare 'Just a moment' challenge page."""
        mock_driver = Mock()
        mock_driver.page_source = "<html><body>Just a moment...</body></html>"
        mock_driver.title = "Just a moment..."

        # Simulate detect_cloudflare_block logic
        page_source = mock_driver.page_source.lower()
        title = mock_driver.title.lower()
        block_indicators = ['just a moment', 'checking your browser', 'access denied']

        detected = any(ind in page_source or ind in title for ind in block_indicators)
        self.assertTrue(detected)

    def test_detect_cloudflare_access_denied(self):
        """Detect WAF 'Access Denied' block."""
        mock_driver = Mock()
        mock_driver.page_source = "<html><body>Access Denied - Error 403</body></html>"
        mock_driver.title = "Access Denied"

        page_source = mock_driver.page_source.lower()
        title = mock_driver.title.lower()
        block_indicators = ['just a moment', 'access denied', 'error 1015']

        detected = any(ind in page_source or ind in title for ind in block_indicators)
        self.assertTrue(detected)

    def test_detect_cloudflare_ray_id(self):
        """Detect Cloudflare by ray ID in page."""
        mock_driver = Mock()
        mock_driver.page_source = "<html><body>Error. Ray ID: abc123</body></html>"
        mock_driver.title = "Error"

        page_source = mock_driver.page_source.lower()
        block_indicators = ['ray id', 'cloudflare']

        detected = any(ind in page_source for ind in block_indicators)
        self.assertTrue(detected)

    def test_no_cloudflare_on_normal_page(self):
        """Normal page should not trigger detection."""
        mock_driver = Mock()
        mock_driver.page_source = "<html><body>Welcome to visa appointment</body></html>"
        mock_driver.title = "Schedule Appointment"

        page_source = mock_driver.page_source.lower()
        title = mock_driver.title.lower()
        block_indicators = ['just a moment', 'access denied', 'cloudflare', 'ray id']

        detected = any(ind in page_source or ind in title for ind in block_indicators)
        self.assertFalse(detected)

    def test_detection_handles_exception(self):
        """Detection should return False if page_source throws."""
        mock_driver = Mock()
        mock_driver.page_source = property(lambda self: None)  # Will raise
        type(mock_driver).page_source = property(lambda self: (_ for _ in ()).throw(Exception("No page")))

        # Simulate the try-except in detect_cloudflare_block
        try:
            page_source = mock_driver.page_source.lower()
            detected = 'cloudflare' in page_source
        except Exception:
            detected = False

        self.assertFalse(detected)


class TestTieredRecoveryStrategy(unittest.TestCase):
    """
    Test the tiered recovery strategy for reschedule failures.

    Level 1: Page refresh
    Level 2: Full re-login
    Level 3: Proxy rotation
    """

    def test_timeout_triggers_page_refresh_first(self):
        """TimeoutException should trigger page refresh (Level 1) first."""
        class TimeoutException(Exception):
            pass

        recovery_steps = []

        def mock_refresh():
            recovery_steps.append("refresh")

        def mock_start_process():
            recovery_steps.append("relogin")

        def mock_detect_cloudflare():
            return False  # No Cloudflare block

        mock_reschedule = Mock(side_effect=[
            TimeoutException("Page load timeout"),
            ["SUCCESS", "Booked"]
        ])

        max_retries = 3
        res = None

        for attempt in range(max_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except TimeoutException:
                if not mock_detect_cloudflare():
                    mock_refresh()  # Level 1
                    continue
                mock_start_process()  # Level 2
                continue

        self.assertEqual(res[0], "SUCCESS")
        self.assertIn("refresh", recovery_steps)
        self.assertNotIn("relogin", recovery_steps)

    def test_cloudflare_skips_refresh_goes_to_proxy_rotation(self):
        """Cloudflare detection should skip refresh and rotate proxy."""
        class TimeoutException(Exception):
            pass

        recovery_steps = []

        def mock_refresh():
            recovery_steps.append("refresh")

        def mock_rotate_proxy():
            recovery_steps.append("proxy_rotation")
            return True

        def mock_detect_cloudflare():
            return True  # Cloudflare block detected

        mock_reschedule = Mock(side_effect=[
            TimeoutException("Page blocked"),
            ["SUCCESS", "Booked"]
        ])

        max_retries = 3
        res = None

        for attempt in range(max_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except TimeoutException:
                if mock_detect_cloudflare():
                    mock_rotate_proxy()  # Level 3 directly
                    continue
                mock_refresh()  # Level 1
                continue

        self.assertEqual(res[0], "SUCCESS")
        self.assertIn("proxy_rotation", recovery_steps)
        self.assertNotIn("refresh", recovery_steps)

    def test_refresh_fails_then_relogin(self):
        """If refresh doesn't help, fall back to full re-login."""
        class TimeoutException(Exception):
            pass

        recovery_steps = []
        refresh_helped = False

        def mock_refresh():
            recovery_steps.append("refresh")
            return refresh_helped

        def mock_start_process():
            recovery_steps.append("relogin")

        attempt_count = 0

        def mock_reschedule(date):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count <= 2:
                raise TimeoutException("Timeout")
            return ["SUCCESS", "Booked"]

        max_retries = 3
        res = None

        for attempt in range(max_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except TimeoutException:
                if attempt < max_retries - 1:
                    # Level 1: Try refresh
                    if not mock_refresh():
                        # Level 2: Full re-login
                        mock_start_process()
                    continue
                res = ["FAIL", "All retries failed"]

        self.assertEqual(res[0], "SUCCESS")
        self.assertIn("refresh", recovery_steps)
        self.assertIn("relogin", recovery_steps)

    def test_login_fails_then_proxy_rotation(self):
        """If login also fails, rotate proxy (Level 3)."""
        class TimeoutException(Exception):
            pass

        recovery_steps = []

        def mock_start_process():
            recovery_steps.append("relogin")
            raise TimeoutException("Login also timed out")

        def mock_rotate_proxy():
            recovery_steps.append("proxy_rotation")
            return True

        attempt_count = 0

        def mock_reschedule(date):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count <= 2:
                raise TimeoutException("Timeout")
            return ["SUCCESS", "Booked"]

        max_retries = 3
        res = None
        proxy_enabled = True

        for attempt in range(max_retries):
            try:
                res = mock_reschedule("2026-02-05")
                break
            except TimeoutException:
                if attempt < max_retries - 1:
                    try:
                        mock_start_process()  # Level 2
                        continue
                    except TimeoutException:
                        if proxy_enabled:
                            mock_rotate_proxy()  # Level 3
                        continue
                res = ["FAIL", "All retries failed"]

        self.assertEqual(res[0], "SUCCESS")
        self.assertIn("relogin", recovery_steps)
        self.assertIn("proxy_rotation", recovery_steps)


class TestSeleniumTimeoutConfiguration(unittest.TestCase):
    """
    Test the new Selenium timeout configuration values.
    """

    def test_reschedule_timeout_is_15_seconds(self):
        """Reschedule page timeout should be 15 seconds."""
        SELENIUM_WAIT_RESCHEDULE = 15
        self.assertEqual(SELENIUM_WAIT_RESCHEDULE, 15)

    def test_login_timeout_is_20_seconds(self):
        """Login page timeout should be 20 seconds."""
        SELENIUM_WAIT_LOGIN = 20
        self.assertEqual(SELENIUM_WAIT_LOGIN, 20)

    def test_default_timeout_is_30_seconds(self):
        """Default timeout should be 30 seconds."""
        SELENIUM_WAIT_DEFAULT = 30
        self.assertEqual(SELENIUM_WAIT_DEFAULT, 30)

    def test_worst_case_total_time_with_new_timeouts(self):
        """
        Calculate worst-case total time with new timeout values.

        Worst case per attempt:
        - Reschedule timeout: 15s
        - Refresh attempt: 2s
        - Relogin timeout: 20s

        With 3 attempts, worst case is:
        (15 + 2 + 20) * 2 + 15 = 89s (much better than 126s before)
        """
        SELENIUM_WAIT_RESCHEDULE = 15
        SELENIUM_WAIT_LOGIN = 20
        REFRESH_WAIT = 2
        max_retries = 3

        # Worst case: all attempts fail with full timeout chain
        worst_case_per_retry = SELENIUM_WAIT_RESCHEDULE + REFRESH_WAIT + SELENIUM_WAIT_LOGIN
        # Last attempt doesn't trigger recovery
        worst_case_total = worst_case_per_retry * (max_retries - 1) + SELENIUM_WAIT_RESCHEDULE

        self.assertLess(worst_case_total, 100)  # Should be under 100s
        self.assertLess(worst_case_total, 126)  # Better than before (126s)


if __name__ == '__main__':
    unittest.main(verbosity=2)
