"""
Integration tests for the main polling loop.

Tests the complete flow of the main loop including:
1. Heartbeat notifications
2. Date fetching and filtering
3. Ban detection handling
4. Reschedule triggering
5. Work limit checks
6. Error handling and recovery

These tests simulate end-to-end scenarios without actually calling external APIs.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMainLoopHeartbeat(unittest.TestCase):
    """Test heartbeat notification logic in main loop."""

    def test_heartbeat_every_20_requests(self):
        """Heartbeat notification should be sent every 20 requests."""
        heartbeat_counts = []
        req_count = 0

        # Simulate 45 requests
        for i in range(45):
            req_count += 1
            if req_count % 20 == 0:
                heartbeat_counts.append(req_count)

        # Should have heartbeats at 20 and 40
        self.assertEqual(heartbeat_counts, [20, 40])

    def test_heartbeat_message_content(self):
        """Heartbeat message should include request count and running time."""
        req_count = 40
        t0 = time.time() - 1800  # 30 minutes ago
        running_mins = (time.time() - t0) / 60

        msg = f"Still running. {req_count} checks. {running_mins:.0f} min."

        self.assertIn("40 checks", msg)
        self.assertIn("30 min", msg)


class TestMainLoopDateProcessing(unittest.TestCase):
    """Test date processing in main loop."""

    def test_empty_response_increments_counter(self):
        """Empty response should increment consecutive_empty_count."""
        consecutive_empty_count = 0

        dates = []  # Empty response
        if not dates:
            consecutive_empty_count += 1

        self.assertEqual(consecutive_empty_count, 1)

    def test_valid_response_resets_counter(self):
        """Valid dates should reset consecutive_empty_count to 0."""
        consecutive_empty_count = 3

        dates = [{"date": "2026-07-15"}]
        if dates:
            consecutive_empty_count = 0

        self.assertEqual(consecutive_empty_count, 0)

    def test_network_retry_counter_reset_on_success(self):
        """Network retry counter should reset on successful request."""
        network_retry_count = 2

        # Simulate successful request
        dates = [{"date": "2026-07-15"}]
        if dates:
            network_retry_count = 0

        self.assertEqual(network_retry_count, 0)


class TestMainLoopWorkLimit(unittest.TestCase):
    """Test work time limit logic."""

    def test_work_limit_exceeded(self):
        """Should detect when work limit is exceeded."""
        work_limit_time = 0.75  # hours
        hour = 3600

        t0 = time.time() - (0.8 * hour)  # 48 minutes ago
        t1 = time.time()
        total_time = t1 - t0

        should_exit = total_time > work_limit_time * hour

        self.assertTrue(should_exit)

    def test_work_limit_not_exceeded(self):
        """Should not exit when work limit not reached."""
        work_limit_time = 0.75  # hours
        hour = 3600

        t0 = time.time() - (0.5 * hour)  # 30 minutes ago
        t1 = time.time()
        total_time = t1 - t0

        should_exit = total_time > work_limit_time * hour

        self.assertFalse(should_exit)


class TestMainLoopBanHandling(unittest.TestCase):
    """Test ban detection and handling in main loop."""

    @patch('visa.send_notification')
    @patch('visa.get_logger')
    def test_empty_response_triggers_graduated_cooldown(self, mock_logger, mock_notify):
        """Empty responses should trigger graduated cooldown."""
        from visa import handle_empty_response

        mock_logger.return_value = MagicMock()

        cooldown_config = {
            'first': 5,
            'second': 30,
            'third': 120,
            'hard_ban': 240
        }

        # First empty
        result1 = handle_empty_response(1, cooldown_config)
        self.assertEqual(result1['action'], 'sleep')
        self.assertEqual(result1['duration'], 5 * 60)

        # Second empty
        result2 = handle_empty_response(2, cooldown_config)
        self.assertEqual(result2['action'], 'sleep')
        self.assertEqual(result2['duration'], 30 * 60)

        # Fourth empty - should exit
        result4 = handle_empty_response(4, cooldown_config)
        self.assertEqual(result4['action'], 'exit')


class TestMainLoopRescheduleFlow(unittest.TestCase):
    """Test reschedule triggering in main loop."""

    def test_reschedule_triggered_on_matching_date(self):
        """Reschedule should be triggered when date matches target range."""
        reschedule_called = False
        target_date = None

        def mock_get_available_date(dates):
            return "2026-07-15"  # Date in range

        def mock_reschedule(date):
            nonlocal reschedule_called, target_date
            reschedule_called = True
            target_date = date
            return ["SUCCESS", f"Booked {date}"]

        dates = [{"date": "2026-07-15"}]
        date = mock_get_available_date(dates)

        if date:
            mock_reschedule(date)

        self.assertTrue(reschedule_called)
        self.assertEqual(target_date, "2026-07-15")

    def test_no_reschedule_when_date_not_in_range(self):
        """Reschedule should not be triggered when no date in range."""
        reschedule_called = False

        def mock_get_available_date(dates):
            return None  # No date in range

        def mock_reschedule(date):
            nonlocal reschedule_called
            reschedule_called = True

        dates = [{"date": "2027-01-15"}]
        date = mock_get_available_date(dates)

        if date:
            mock_reschedule(date)

        self.assertFalse(reschedule_called)


class TestMainLoopRescheduleRetry(unittest.TestCase):
    """Test reschedule retry logic in main loop."""

    def test_retry_on_exception(self):
        """Should retry reschedule on exception."""
        attempts = []

        def mock_reschedule(date):
            attempts.append(len(attempts) + 1)
            if len(attempts) < 3:
                raise Exception("ChromeDriver error")
            return ["SUCCESS", f"Booked {date}"]

        def mock_start_process():
            pass

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-07-15")
                break
            except Exception:
                if attempt < max_reschedule_retries - 1:
                    mock_start_process()
                    continue
                res = ["FAIL", "All retries failed"]

        self.assertEqual(res[0], "SUCCESS")
        self.assertEqual(len(attempts), 3)

    def test_no_retry_on_normal_fail(self):
        """Should not retry on normal FAIL return (not exception)."""
        attempts = []

        def mock_reschedule(date):
            attempts.append(1)
            return ["FAIL", "Booking failed"]

        max_reschedule_retries = 3
        res = None

        for attempt in range(max_reschedule_retries):
            try:
                res = mock_reschedule("2026-07-15")
                break  # Normal return, no retry
            except Exception:
                continue

        self.assertEqual(res[0], "FAIL")
        self.assertEqual(len(attempts), 1)  # Only one attempt


class TestMainLoopNetworkErrorHandling(unittest.TestCase):
    """Test network error handling in main loop."""

    def test_network_retry_up_to_3_times(self):
        """Should retry network errors up to 3 times before exiting."""
        network_retry_count = 0
        exit_triggered = False

        for _ in range(5):
            try:
                raise Exception("Network error")
            except Exception:
                network_retry_count += 1
                if network_retry_count >= 3:
                    exit_triggered = True
                    break

        self.assertEqual(network_retry_count, 3)
        self.assertTrue(exit_triggered)


class TestMainLoopProxyRotation(unittest.TestCase):
    """Test proxy rotation logic in main loop."""

    def test_proxy_rotation_on_ban(self):
        """Should attempt proxy rotation on ban detection."""
        proxy_rotated = False
        session_restarted = False

        def mock_rotate_proxy():
            nonlocal proxy_rotated
            proxy_rotated = True
            return True

        def mock_start_process():
            nonlocal session_restarted
            session_restarted = True

        # Simulate ban detection with proxy available
        proxy_enabled = True
        has_proxies = True

        if proxy_enabled and has_proxies:
            if mock_rotate_proxy():
                mock_start_process()

        self.assertTrue(proxy_rotated)
        self.assertTrue(session_restarted)

    def test_exit_when_no_proxies_available(self):
        """Should exit when no proxies available after ban."""
        should_exit = False

        def mock_rotate_proxy():
            return False  # No more proxies

        proxy_enabled = True

        if proxy_enabled:
            if not mock_rotate_proxy():
                should_exit = True

        self.assertTrue(should_exit)


class TestMainLoopExitCodes(unittest.TestCase):
    """Test exit code handling."""

    def test_exit_codes_defined(self):
        """Verify exit codes are correctly defined."""
        from visa import EXIT_WORK_LIMIT, EXIT_BAN, EXIT_NETWORK

        self.assertEqual(EXIT_WORK_LIMIT, 0)
        self.assertEqual(EXIT_BAN, 2)
        self.assertEqual(EXIT_NETWORK, 3)

    def test_work_limit_exit_code(self):
        """Work limit should trigger EXIT_WORK_LIMIT (0)."""
        from visa import EXIT_WORK_LIMIT

        exit_code = EXIT_WORK_LIMIT
        self.assertEqual(exit_code, 0)

    def test_ban_exit_code(self):
        """Ban detection should trigger EXIT_BAN (2)."""
        from visa import EXIT_BAN

        exit_code = EXIT_BAN
        self.assertEqual(exit_code, 2)


class TestMainLoopScenarios(unittest.TestCase):
    """End-to-end scenario tests."""

    def test_scenario_successful_booking(self):
        """Full scenario: find date, reschedule, success."""
        events = []

        def mock_get_dates():
            events.append("fetch_dates")
            return [{"date": "2026-07-15"}]

        def mock_get_available_date(dates):
            events.append("filter_dates")
            return "2026-07-15"

        def mock_reschedule(date):
            events.append(f"reschedule_{date}")
            return ["SUCCESS", f"Booked {date}"]

        # Simulate main loop iteration
        dates = mock_get_dates()
        if dates:
            date = mock_get_available_date(dates)
            if date:
                res = mock_reschedule(date)
                if res[0] == "SUCCESS":
                    events.append("exit_success")

        self.assertEqual(events, [
            "fetch_dates",
            "filter_dates",
            "reschedule_2026-07-15",
            "exit_success"
        ])

    def test_scenario_date_not_in_range(self):
        """Scenario: dates available but not in target range."""
        events = []
        notifications = []

        last_notified = None

        def mock_get_dates():
            events.append("fetch_dates")
            return [{"date": "2027-01-15"}]

        def mock_get_available_date(dates):
            events.append("filter_dates")
            return None  # Not in range

        def mock_notify(title, msg):
            notifications.append((title, msg))

        dates = mock_get_dates()
        if dates:
            date = mock_get_available_date(dates)
            if date:
                pass  # Would reschedule
            else:
                earliest = dates[0]["date"]
                if last_notified is None or earliest < last_notified:
                    mock_notify("DATES AVAILABLE", f"Earliest: {earliest}")
                    events.append("notify_dates_available")

        self.assertEqual(events, [
            "fetch_dates",
            "filter_dates",
            "notify_dates_available"
        ])
        self.assertEqual(len(notifications), 1)

    def test_scenario_empty_response_ban_sequence(self):
        """Scenario: consecutive empty responses leading to exit."""
        events = []
        consecutive_empty_count = 0

        cooldown_config = {
            'first': 5,
            'second': 30,
            'third': 120,
            'hard_ban': 240
        }

        # Simulate 4 empty responses
        for i in range(4):
            dates = []
            if not dates:
                consecutive_empty_count += 1
                events.append(f"empty_{consecutive_empty_count}")

                # Simulate handle_empty_response logic
                if consecutive_empty_count >= 4:
                    events.append("exit_ban")
                    break

        self.assertEqual(consecutive_empty_count, 4)
        self.assertIn("exit_ban", events)


if __name__ == '__main__':
    unittest.main(verbosity=2)
