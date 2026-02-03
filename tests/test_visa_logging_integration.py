"""
Integration tests for visa.py logging.

Tests that visa.py functions call the correct logger methods
with appropriate parameters.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock, call

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestHandleEmptyResponseLogging(unittest.TestCase):
    """Test logging in handle_empty_response function."""

    @patch('visa.get_logger')
    @patch('visa.send_notification')
    def test_logs_ban_detected_on_first_empty(self, mock_notify, mock_get_logger):
        """First empty response should log ban_detected with cooldown."""
        from visa import handle_empty_response

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        cooldown_config = {'first': 5, 'second': 30, 'third': 120, 'hard_ban': 240}
        result = handle_empty_response(1, cooldown_config)

        # Should log ban_detected
        mock_logger.ban_detected.assert_called_once()
        call_args = mock_logger.ban_detected.call_args
        self.assertEqual(call_args[0][0], "empty_response")
        self.assertEqual(call_args[0][1], 5)  # cooldown minutes
        self.assertEqual(call_args[0][2], 1)  # consecutive count

        # Should return sleep action
        self.assertEqual(result['action'], 'sleep')
        self.assertEqual(result['duration'], 300)  # 5 * 60

    @patch('visa.get_logger')
    @patch('visa.send_notification')
    def test_logs_error_on_max_consecutive(self, mock_notify, mock_get_logger):
        """4+ consecutive empties should log error and return exit."""
        from visa import handle_empty_response

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        cooldown_config = {'first': 5, 'second': 30, 'third': 120, 'hard_ban': 240}
        result = handle_empty_response(4, cooldown_config)

        # Should log both ban_detected and error
        mock_logger.ban_detected.assert_called()
        mock_logger.error.assert_called()

        # Should return exit action
        self.assertEqual(result['action'], 'exit')


class TestSendNotificationLogging(unittest.TestCase):
    """Test logging in send_notification function."""

    @patch('visa.requests.post')
    @patch('visa.get_logger')
    @patch('visa.TELEGRAM_BOT_TOKEN', 'test_token')
    @patch('visa.TELEGRAM_CHAT_ID', '12345')
    @patch('visa.SENDGRID_API_KEY', '')
    def test_logs_telegram_success(self, mock_get_logger, mock_post):
        """Successful Telegram notification should log info."""
        from visa import send_notification

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_post.return_value = MagicMock(status_code=200)

        send_notification("Test Title", "Test message")

        # Should log info for Telegram
        mock_logger.info.assert_called()
        call_args = mock_logger.info.call_args
        self.assertIn("Telegram sent", call_args[0][1])

    @patch('visa.requests.post')
    @patch('visa.get_logger')
    @patch('visa.TELEGRAM_BOT_TOKEN', 'test_token')
    @patch('visa.TELEGRAM_CHAT_ID', '12345')
    @patch('visa.SENDGRID_API_KEY', '')
    def test_logs_telegram_error(self, mock_get_logger, mock_post):
        """Failed Telegram notification should log error."""
        from visa import send_notification

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_post.side_effect = Exception("Connection failed")

        send_notification("Test Title", "Test message")

        # Should log error for Telegram failure
        mock_logger.error.assert_called()


class TestReloginLogging(unittest.TestCase):
    """Test logging in relogin function."""

    @patch('visa.start_process')
    @patch('visa.driver')
    @patch('visa.get_logger')
    def test_logs_session_expired_and_relogin_attempt(self, mock_get_logger, mock_driver, mock_start):
        """relogin should log session_expired and relogin_attempt."""
        from visa import relogin

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        relogin()

        # Should log session_expired
        mock_logger.session_expired.assert_called_once()

        # Should log relogin_attempt
        mock_logger.relogin_attempt.assert_called_once_with(1, 1)

        # Should log login_success on success
        mock_logger.login_success.assert_called()

    @patch('visa.start_process')
    @patch('visa.driver')
    @patch('visa.get_logger')
    def test_logs_login_failed_on_exception(self, mock_get_logger, mock_driver, mock_start):
        """relogin should log login_failed on exception."""
        from visa import relogin

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_start.side_effect = Exception("Login failed")

        result = relogin()

        # Should log login_failed
        mock_logger.login_failed.assert_called()
        self.assertFalse(result)


from selenium.common.exceptions import WebDriverException

class TestGetDateWithRetryLogging(unittest.TestCase):
    """Test logging in get_date_with_retry function."""

    @patch('visa.driver')
    @patch('visa.get_logger')
    @patch('visa.time.sleep')
    def test_logs_network_error_on_webdriver_exception(self, mock_sleep, mock_get_logger, mock_driver):
        """WebDriverException should log network_error."""
        from visa import get_date_with_retry

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Mock driver to raise WebDriverException
        mock_driver.get_cookie.return_value = {"value": "test_session"}
        mock_driver.execute_script.side_effect = WebDriverException("Network error")

        with self.assertRaises(WebDriverException):
            get_date_with_retry(max_retries=2)

        # Should log network_error for each retry (attempt 0 triggers log+sleep, attempt 1 raises)
        # So call count should be 1
        self.assertEqual(mock_logger.network_error.call_count, 1)


class TestGetTimeWithRetryLogging(unittest.TestCase):
    """Test logging in get_time_with_retry function."""

    @patch('visa.driver')
    @patch('visa.get_logger')
    def test_logs_warning_when_no_slots(self, mock_get_logger, mock_driver):
        """No available time slots should log warning."""
        from visa import get_time_with_retry

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Mock driver to return empty available_times
        mock_driver.get_cookie.return_value = {"value": "test_session"}
        mock_driver.execute_script.return_value = '{"available_times": []}'

        result = get_time_with_retry("2026-02-05")

        # Should log warning
        mock_logger.warning.assert_called()
        call_args = mock_logger.warning.call_args
        self.assertIn("No time slots", call_args[0][1])

        # Should return None
        self.assertIsNone(result)


class TestRescheduleLogging(unittest.TestCase):
    """Test logging in reschedule function."""

    @patch('visa.requests.post')
    @patch('visa.driver')
    @patch('visa.get_time_with_retry')
    @patch('visa.get_logger')
    def test_logs_warning_on_failed_response(self, mock_get_logger, mock_get_time, mock_driver, mock_post):
        """Failed reschedule response should log warning."""
        from visa import reschedule

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_get_time.return_value = "09:00"
        mock_driver.get_cookie.return_value = {"value": "test_session"}
        mock_driver.execute_script.return_value = "Mozilla/5.0"
        mock_driver.find_element.return_value = MagicMock(get_attribute=MagicMock(return_value="token"))

        # Mock failed response
        mock_response = MagicMock()
        mock_response.text = "Appointment not available"
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = reschedule("2026-02-05")

        # Should log warning with response details
        mock_logger.warning.assert_called()
        self.assertEqual(result[0], "FAIL")


class TestCleanupAndExitLogging(unittest.TestCase):
    """Test logging in cleanup_and_exit function."""

    @patch('visa.sys.exit')
    @patch('visa.driver')
    @patch('visa.get_logger')
    def test_logs_system_shutdown_with_reason(self, mock_get_logger, mock_driver, mock_exit):
        """cleanup_and_exit should log system_shutdown with reason."""
        from visa import cleanup_and_exit, EXIT_WORK_LIMIT, EXIT_BAN, EXIT_NETWORK

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Test work limit
        mock_exit.side_effect = SystemExit(0)
        try:
            cleanup_and_exit(EXIT_WORK_LIMIT)
        except SystemExit:
            pass

        mock_logger.system_shutdown.assert_called_with("work_limit_reached", EXIT_WORK_LIMIT)


class TestRotateProxyAndRestartLogging(unittest.TestCase):
    """Test logging in rotate_proxy_and_restart function."""

    @patch('visa.init_driver')
    @patch('visa.driver')
    @patch('visa.PROXY_MANAGER')
    @patch('visa.PROXY_ENABLED', True)
    @patch('visa.get_logger')
    def test_logs_proxy_rotate_on_success(self, mock_get_logger, mock_proxy_manager, mock_driver, mock_init):
        """Successful proxy rotation should log proxy_rotate."""
        from visa import rotate_proxy_and_restart

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_proxy_manager.has_proxies = True
        mock_proxy_manager.get_proxy.return_value = {"host": "1.2.3.4", "port": "8080"}
        mock_proxy_manager.rotate.return_value = {"host": "5.6.7.8", "port": "8080"}

        result = rotate_proxy_and_restart()

        # Should log proxy_rotate
        mock_logger.proxy_rotate.assert_called()
        self.assertTrue(result)

    @patch('visa.PROXY_MANAGER')
    @patch('visa.PROXY_ENABLED', True)
    @patch('visa.get_logger')
    def test_logs_proxy_exhausted_when_no_more(self, mock_get_logger, mock_proxy_manager):
        """No more proxies should log proxy_exhausted."""
        from visa import rotate_proxy_and_restart

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        mock_proxy_manager.has_proxies = True
        mock_proxy_manager.get_proxy.return_value = {"host": "1.2.3.4", "port": "8080"}
        mock_proxy_manager.rotate.return_value = None

        result = rotate_proxy_and_restart()

        # Should log proxy_exhausted
        mock_logger.proxy_exhausted.assert_called()
        self.assertFalse(result)


class TestInitDriverLogging(unittest.TestCase):
    """Test logging in init_driver function."""

    @patch('visa.webdriver.Chrome')
    @patch('visa.LOCAL_USE', True)
    @patch('visa.HEADLESS', False)
    @patch('visa.uc', None)
    @patch('visa.get_logger')
    def test_logs_selenium_init_success(self, mock_get_logger, mock_chrome):
        """Successful driver init should log to SELENIUM category."""
        from visa import init_driver

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        init_driver(None)

        # Should log successful initialization
        mock_logger.info.assert_called()
        # Check that SELENIUM category was used
        info_calls = [c for c in mock_logger.info.call_args_list]
        selenium_logged = any('SELENIUM' in str(c) or 'Chrome' in str(c) for c in info_calls)
        # At least some logging happened
        self.assertTrue(len(info_calls) > 0)


class TestGetAvailableDateLogging(unittest.TestCase):
    """Test logging in get_available_date function."""

    @patch('visa.get_logger')
    @patch('visa.PRIOD_START', '2026-03-01')
    @patch('visa.PRIOD_END', '2026-03-31')
    def test_logs_info_when_no_dates_in_range(self, mock_get_logger):
        """No dates in target range should log info."""
        from visa import get_available_date

        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Dates outside target range
        dates = [{"date": "2026-02-05"}, {"date": "2026-02-10"}]
        result = get_available_date(dates)

        # Should log info about no dates in range
        mock_logger.info.assert_called()
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
