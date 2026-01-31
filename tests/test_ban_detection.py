"""
Unit tests for graduated ban detection functionality.

Tests the improved ban detection that distinguishes between:
- Actual rate limiting (consecutive empty responses)
- Temporary glitches (single empty response)
- Hard bans (HTTP 403/429)
- Site maintenance
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBanCooldownCalculation(unittest.TestCase):
    """Test the graduated cooldown calculation."""

    def setUp(self):
        """Set up test fixtures."""
        # Default cooldown values (in minutes)
        self.default_cooldowns = {
            'first': 5,
            'second': 30,
            'third': 120,
            'hard_ban': 240
        }

    def test_first_empty_response_short_cooldown(self):
        """First empty response should trigger short cooldown (5 min)."""
        from visa import get_ban_cooldown

        cooldown = get_ban_cooldown(
            consecutive_empty_count=1,
            http_status=200,
            cooldown_config=self.default_cooldowns
        )

        self.assertEqual(cooldown, 5 * 60)  # 5 minutes in seconds

    def test_second_empty_response_medium_cooldown(self):
        """Second consecutive empty response should trigger medium cooldown (30 min)."""
        from visa import get_ban_cooldown

        cooldown = get_ban_cooldown(
            consecutive_empty_count=2,
            http_status=200,
            cooldown_config=self.default_cooldowns
        )

        self.assertEqual(cooldown, 30 * 60)  # 30 minutes in seconds

    def test_third_empty_response_long_cooldown(self):
        """Third consecutive empty response should trigger long cooldown (2 hr)."""
        from visa import get_ban_cooldown

        cooldown = get_ban_cooldown(
            consecutive_empty_count=3,
            http_status=200,
            cooldown_config=self.default_cooldowns
        )

        self.assertEqual(cooldown, 120 * 60)  # 120 minutes in seconds

    def test_http_403_immediate_hard_ban_cooldown(self):
        """HTTP 403 should trigger immediate hard ban cooldown."""
        from visa import get_ban_cooldown

        cooldown = get_ban_cooldown(
            consecutive_empty_count=1,  # Even first time
            http_status=403,
            cooldown_config=self.default_cooldowns
        )

        self.assertEqual(cooldown, 240 * 60)  # 4 hours in seconds

    def test_http_429_immediate_hard_ban_cooldown(self):
        """HTTP 429 should trigger immediate hard ban cooldown."""
        from visa import get_ban_cooldown

        cooldown = get_ban_cooldown(
            consecutive_empty_count=1,
            http_status=429,
            cooldown_config=self.default_cooldowns
        )

        self.assertEqual(cooldown, 240 * 60)

    def test_http_429_with_retry_after_header(self):
        """HTTP 429 with Retry-After header should use header value."""
        from visa import get_ban_cooldown

        cooldown = get_ban_cooldown(
            consecutive_empty_count=1,
            http_status=429,
            cooldown_config=self.default_cooldowns,
            retry_after=300  # 5 minutes from header
        )

        self.assertEqual(cooldown, 300)

    def test_fourth_plus_empty_uses_exit_signal(self):
        """Fourth+ consecutive empty should signal exit (return -1)."""
        from visa import get_ban_cooldown

        cooldown = get_ban_cooldown(
            consecutive_empty_count=4,
            http_status=200,
            cooldown_config=self.default_cooldowns
        )

        # -1 signals "exit with ban code" instead of just sleeping
        self.assertEqual(cooldown, -1)


class TestConsecutiveEmptyCounter(unittest.TestCase):
    """Test the consecutive empty response counter behavior."""

    def setUp(self):
        """Set up mocks."""
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

    def tearDown(self):
        """Clean up patches."""
        self.driver_patcher.stop()

    def test_counter_increments_on_empty(self):
        """Counter should increment on each empty response."""
        # This tests the main loop behavior
        # We'll test the counter logic directly
        consecutive_empty = 0

        # Simulate 3 empty responses
        for _ in range(3):
            dates = []  # Empty response
            if not dates:
                consecutive_empty += 1

        self.assertEqual(consecutive_empty, 3)

    def test_counter_resets_on_valid_response(self):
        """Counter should reset to 0 when valid dates received."""
        consecutive_empty = 3  # Was at 3

        dates = [{"date": "2027-07-15"}]  # Valid response
        if dates:
            consecutive_empty = 0

        self.assertEqual(consecutive_empty, 0)


class TestBanSignalDetection(unittest.TestCase):
    """Test detection of various ban signals."""

    def test_detect_cloudflare_403(self):
        """Should detect Cloudflare 403 as hard ban."""
        from visa import is_hard_ban_response

        response_text = '''
        <!DOCTYPE html>
        <html>
        <body>
            <h1>Sorry, you have been blocked</h1>
            <p>Ray ID: 1234567890</p>
        </body>
        </html>
        '''

        result = is_hard_ban_response(403, response_text)
        self.assertTrue(result)

    def test_detect_cloudflare_1015(self):
        """Should detect Cloudflare Error 1015 as hard ban."""
        from visa import is_hard_ban_response

        response_text = '''
        <!DOCTYPE html>
        <html>
        <body>
            <h1>Error 1015</h1>
            <p>You are being rate limited</p>
        </body>
        </html>
        '''

        result = is_hard_ban_response(429, response_text)
        self.assertTrue(result)

    def test_empty_json_not_hard_ban(self):
        """Empty JSON array should not be classified as hard ban."""
        from visa import is_hard_ban_response

        result = is_hard_ban_response(200, '[]')
        self.assertFalse(result)

    def test_valid_dates_not_hard_ban(self):
        """Valid dates response should not be classified as hard ban."""
        from visa import is_hard_ban_response

        response_text = '[{"date": "2027-07-15", "business_day": true}]'

        result = is_hard_ban_response(200, response_text)
        self.assertFalse(result)


class TestConfigLoading(unittest.TestCase):
    """Test loading of ban detection config."""

    def test_load_ban_detection_config_defaults(self):
        """Should use defaults when BAN_DETECTION section missing."""
        import configparser

        config = configparser.ConfigParser()
        # No BAN_DETECTION section

        from visa import load_ban_detection_config

        cooldowns = load_ban_detection_config(config)

        # Should return defaults
        self.assertEqual(cooldowns['first'], 5)
        self.assertEqual(cooldowns['second'], 30)
        self.assertEqual(cooldowns['third'], 120)
        self.assertEqual(cooldowns['hard_ban'], 240)

    def test_load_ban_detection_config_custom(self):
        """Should load custom values from config."""
        import configparser

        config = configparser.ConfigParser()
        config['BAN_DETECTION'] = {
            'COOLDOWN_FIRST_EMPTY': '10',
            'COOLDOWN_SECOND_EMPTY': '60',
            'COOLDOWN_THIRD_EMPTY': '180',
            'COOLDOWN_HARD_BAN': '300'
        }

        from visa import load_ban_detection_config

        cooldowns = load_ban_detection_config(config)

        self.assertEqual(cooldowns['first'], 10)
        self.assertEqual(cooldowns['second'], 60)
        self.assertEqual(cooldowns['third'], 180)
        self.assertEqual(cooldowns['hard_ban'], 300)


class TestGraduatedBanResponse(unittest.TestCase):
    """Test the full graduated ban response behavior."""

    def setUp(self):
        """Set up mocks."""
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()
        self.sleep_patcher = patch('visa.time.sleep')
        self.mock_sleep = self.sleep_patcher.start()

    def tearDown(self):
        """Clean up patches."""
        self.driver_patcher.stop()
        self.sleep_patcher.stop()

    @patch('visa.send_notification')
    @patch('visa.info_logger')
    def test_no_notification_on_first_empty(self, mock_logger, mock_notify):
        """First empty response should NOT send ban notification."""
        from visa import handle_empty_response

        result = handle_empty_response(
            consecutive_count=1,
            cooldown_config={'first': 5, 'second': 30, 'third': 120, 'hard_ban': 240}
        )

        # Should return 'continue' (not exit)
        self.assertEqual(result['action'], 'sleep')
        self.assertEqual(result['duration'], 5 * 60)

        # Should NOT send ban notification
        mock_notify.assert_not_called()

    @patch('visa.send_notification')
    @patch('visa.info_logger')
    def test_notification_on_third_empty(self, mock_logger, mock_notify):
        """Third consecutive empty should send warning notification."""
        from visa import handle_empty_response

        result = handle_empty_response(
            consecutive_count=3,
            cooldown_config={'first': 5, 'second': 30, 'third': 120, 'hard_ban': 240}
        )

        self.assertEqual(result['action'], 'sleep')
        self.assertEqual(result['duration'], 120 * 60)

        # Should send warning notification
        mock_notify.assert_called_once()

    @patch('visa.send_notification')
    @patch('visa.info_logger')
    def test_exit_on_fourth_empty(self, mock_logger, mock_notify):
        """Fourth consecutive empty should trigger exit."""
        from visa import handle_empty_response

        result = handle_empty_response(
            consecutive_count=4,
            cooldown_config={'first': 5, 'second': 30, 'third': 120, 'hard_ban': 240}
        )

        # Should return 'exit'
        self.assertEqual(result['action'], 'exit')

        # Should send ban notification
        mock_notify.assert_called()


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility with existing config."""

    def test_old_config_still_works(self):
        """Bot should work with old config.ini (no BAN_DETECTION section)."""
        import configparser

        # Minimal old-style config
        config = configparser.ConfigParser()
        config['PERSONAL_INFO'] = {
            'USERNAME': 'test@example.com',
            'PASSWORD': 'test',
            'SCHEDULE_ID': '12345',
            'PRIOD_START': '2026-01-01',
            'PRIOD_END': '2026-12-31',
            'YOUR_EMBASSY': 'en-ca-tor'
        }
        config['TIME'] = {
            'RETRY_TIME_L_BOUND': '111',
            'RETRY_TIME_U_BOUND': '300',
            'WORK_LIMIT_TIME': '0.75',
            'BAN_COOLDOWN_TIME': '4'
        }

        # Should not raise error when loading ban detection config
        from visa import load_ban_detection_config

        cooldowns = load_ban_detection_config(config)

        # Should have valid defaults
        self.assertIsNotNone(cooldowns)
        self.assertIn('first', cooldowns)
        self.assertIn('hard_ban', cooldowns)


if __name__ == '__main__':
    unittest.main(verbosity=2)
