"""
Unit tests for session management functionality.
Tests the auto re-login feature when session expires.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os

# Add parent directory to path to import visa module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSessionExpirationDetection(unittest.TestCase):
    """Test session expiration error detection."""

    def setUp(self):
        """Import the function we're testing."""
        # We need to mock the driver before importing visa
        with patch('visa.driver'):
            import visa
            self.visa = visa

    def test_detect_empty_json_error(self):
        """Test detection of empty JSON response error."""
        error = json.JSONDecodeError("Expecting value: line 1 column 1 (char 0)", "", 0)
        result = self.visa.is_session_expired_error(error)
        self.assertTrue(result, "Should detect empty JSON as session error")

    def test_detect_401_error(self):
        """Test detection of 401 unauthorized error."""
        error = Exception("HTTP 401 Unauthorized")
        result = self.visa.is_session_expired_error(error)
        self.assertTrue(result, "Should detect 401 as session error")

    def test_detect_403_error(self):
        """Test detection of 403 forbidden error."""
        error = Exception("HTTP 403 Forbidden")
        result = self.visa.is_session_expired_error(error)
        self.assertTrue(result, "Should detect 403 as session error")

    def test_detect_session_expired_message(self):
        """Test detection of explicit session expired message."""
        error = Exception("Session expired, please login again")
        result = self.visa.is_session_expired_error(error)
        self.assertTrue(result, "Should detect 'session expired' message")

    def test_ignore_other_errors(self):
        """Test that other errors are not classified as session errors."""
        error = Exception("Network timeout")
        result = self.visa.is_session_expired_error(error)
        self.assertFalse(result, "Should not detect network timeout as session error")

    def test_ignore_value_errors(self):
        """Test that generic value errors are not classified as session errors."""
        error = ValueError("Invalid date format")
        result = self.visa.is_session_expired_error(error)
        self.assertFalse(result, "Should not detect value error as session error")


class TestGetDateWithRetry(unittest.TestCase):
    """Test get_date_with_retry function."""

    def setUp(self):
        """Set up mocks for testing."""
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        # Import visa after patching driver
        import visa
        self.visa = visa

    def tearDown(self):
        """Clean up patches."""
        self.driver_patcher.stop()

    @patch('visa.relogin')
    def test_successful_first_attempt(self, mock_relogin):
        """Test successful API call on first attempt."""
        # Mock successful response
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.return_value = '[{"date": "2027-07-01"}]'

        result = self.visa.get_date_with_retry()

        self.assertEqual(result, [{"date": "2027-07-01"}])
        self.assertEqual(self.mock_driver.execute_script.call_count, 1)
        mock_relogin.assert_not_called()

    @patch('visa.relogin')
    def test_retry_on_empty_response(self, mock_relogin):
        """Test retry when API returns empty response."""
        # First attempt returns empty, second returns valid data
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.side_effect = [
            '',  # Empty response (session expired)
            '[{"date": "2027-07-01"}]'  # Valid response after re-login
        ]
        mock_relogin.return_value = True

        result = self.visa.get_date_with_retry()

        self.assertEqual(result, [{"date": "2027-07-01"}])
        self.assertEqual(self.mock_driver.execute_script.call_count, 2)
        mock_relogin.assert_called_once()

    @patch('visa.relogin')
    def test_retry_on_json_error(self, mock_relogin):
        """Test retry when JSON parsing fails."""
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.side_effect = [
            'invalid json',  # Invalid JSON (session expired)
            '[{"date": "2027-07-01"}]'  # Valid response after re-login
        ]
        mock_relogin.return_value = True

        result = self.visa.get_date_with_retry()

        self.assertEqual(result, [{"date": "2027-07-01"}])
        self.assertEqual(self.mock_driver.execute_script.call_count, 2)
        mock_relogin.assert_called_once()

    @patch('visa.relogin')
    def test_fail_after_max_retries(self, mock_relogin):
        """Test that function raises error after max retries."""
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.return_value = ''
        mock_relogin.return_value = True

        with self.assertRaises(ValueError):
            self.visa.get_date_with_retry(max_retries=2)

        # Should try twice (initial + 1 retry)
        self.assertEqual(self.mock_driver.execute_script.call_count, 2)
        # Should only relogin once (between first and second attempt)
        self.assertEqual(mock_relogin.call_count, 1)

    @patch('visa.relogin')
    def test_fail_on_relogin_failure(self, mock_relogin):
        """Test that function raises error if re-login fails."""
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.return_value = ''
        mock_relogin.return_value = False  # Re-login fails

        with self.assertRaises(ValueError):
            self.visa.get_date_with_retry()

        self.assertEqual(self.mock_driver.execute_script.call_count, 1)
        mock_relogin.assert_called_once()

    @patch('visa.relogin')
    def test_no_retry_on_non_session_error(self, mock_relogin):
        """Test that non-session errors are not retried."""
        self.mock_driver.get_cookie.side_effect = KeyError("Cookie not found")

        with self.assertRaises(KeyError):
            self.visa.get_date_with_retry()

        mock_relogin.assert_not_called()


class TestGetTimeWithRetry(unittest.TestCase):
    """Test get_time_with_retry function."""

    def setUp(self):
        """Set up mocks for testing."""
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        # Import visa after patching driver
        import visa
        self.visa = visa

    def tearDown(self):
        """Clean up patches."""
        self.driver_patcher.stop()

    @patch('visa.relogin')
    def test_successful_first_attempt(self, mock_relogin):
        """Test successful API call on first attempt."""
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.return_value = '{"available_times": ["09:00", "10:00"]}'

        result = self.visa.get_time_with_retry("2027-07-01")

        self.assertEqual(result, "10:00")
        self.assertEqual(self.mock_driver.execute_script.call_count, 1)
        mock_relogin.assert_not_called()

    @patch('visa.relogin')
    @patch('builtins.print')
    def test_retry_on_empty_response(self, mock_print, mock_relogin):
        """Test retry when API returns empty response."""
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.side_effect = [
            '',  # Empty response (session expired)
            '{"available_times": ["09:00", "10:00"]}'  # Valid response
        ]
        mock_relogin.return_value = True

        result = self.visa.get_time_with_retry("2027-07-01")

        self.assertEqual(result, "10:00")
        self.assertEqual(self.mock_driver.execute_script.call_count, 2)
        mock_relogin.assert_called_once()

    @patch('visa.relogin')
    def test_fail_after_max_retries(self, mock_relogin):
        """Test that function raises error after max retries."""
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.return_value = ''
        mock_relogin.return_value = True

        with self.assertRaises(ValueError):
            self.visa.get_time_with_retry("2027-07-01", max_retries=2)

        self.assertEqual(self.mock_driver.execute_script.call_count, 2)
        self.assertEqual(mock_relogin.call_count, 1)


class TestReloginFunction(unittest.TestCase):
    """Test relogin function."""

    def setUp(self):
        """Set up mocks for testing."""
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        # Import visa after patching driver
        import visa
        self.visa = visa

    def tearDown(self):
        """Clean up patches."""
        self.driver_patcher.stop()

    @patch('visa.start_process')
    @patch('visa.info_logger')
    @patch('visa.os.path.join')
    @patch('builtins.print')
    def test_successful_relogin(self, mock_print, mock_join, mock_logger, mock_start):
        """Test successful re-login."""
        mock_join.return_value = "test_log.txt"

        result = self.visa.relogin()

        self.assertTrue(result)
        self.mock_driver.get.assert_called()  # Should call sign out
        mock_start.assert_called_once()

    @patch('visa.start_process')
    @patch('visa.info_logger')
    @patch('visa.os.path.join')
    @patch('builtins.print')
    def test_relogin_failure(self, mock_print, mock_join, mock_logger, mock_start):
        """Test re-login failure."""
        mock_join.return_value = "test_log.txt"
        mock_start.side_effect = Exception("Login failed")

        result = self.visa.relogin()

        self.assertFalse(result)
        mock_logger.assert_called()  # Should log the error


class TestIntegration(unittest.TestCase):
    """Integration tests for session management."""

    def setUp(self):
        """Set up mocks for integration testing."""
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        # Import visa after patching driver
        import visa
        self.visa = visa

    def tearDown(self):
        """Clean up patches."""
        self.driver_patcher.stop()

    @patch('visa.start_process')
    @patch('visa.info_logger')
    @patch('visa.os.path.join')
    @patch('builtins.print')
    def test_full_session_expiration_recovery(self, mock_print, mock_join, mock_logger, mock_start):
        """Test complete flow of session expiration and recovery."""
        mock_join.return_value = "test_log.txt"

        # Simulate session expiration scenario
        self.mock_driver.get_cookie.return_value = {"value": "old_session"}
        self.mock_driver.execute_script.side_effect = [
            '',  # First call: empty response (session expired)
            '[{"date": "2027-07-01"}]'  # Second call: success after relogin
        ]

        result = self.visa.get_date_with_retry()

        # Verify the result
        self.assertEqual(result, [{"date": "2027-07-01"}])

        # Verify re-login was triggered
        mock_start.assert_called_once()
        self.mock_driver.get.assert_called()  # Sign out was called

        # Verify logging
        self.assertTrue(mock_logger.called)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
