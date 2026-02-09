"""
Unit tests for the reschedule function.

Tests the core booking logic that submits appointment reschedule requests.

Key scenarios tested:
1. Successful reschedule
2. No time slots available (NO_SLOTS)
3. Session cookie missing
4. Authenticity token not found
5. HTTP request timeout
6. Network errors
7. Success detection (case-insensitive)
8. Failed booking responses
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRescheduleSuccess(unittest.TestCase):
    """Test successful reschedule scenarios."""

    def setUp(self):
        """Set up mocks for successful reschedule."""
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        self.requests_patcher = patch('visa.requests')
        self.mock_requests = self.requests_patcher.start()

        self.get_time_patcher = patch('visa.get_time_with_retry')
        self.mock_get_time = self.get_time_patcher.start()

        self.logger_patcher = patch('visa.get_logger')
        self.mock_logger = self.logger_patcher.start()
        self.mock_logger.return_value = MagicMock()

        self.sleep_patcher = patch('visa.time.sleep')
        self.mock_sleep = self.sleep_patcher.start()

        self.wait_patcher = patch('visa.Wait')
        self.mock_wait = self.wait_patcher.start()

        # Configure default successful mocks
        self.mock_get_time.return_value = "09:00"
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.return_value = "Mozilla/5.0..."

        # Mock authenticity token element
        mock_token_element = MagicMock()
        mock_token_element.get_attribute.return_value = "test_auth_token"
        self.mock_driver.find_element.return_value = mock_token_element

    def tearDown(self):
        """Clean up patches."""
        self.driver_patcher.stop()
        self.requests_patcher.stop()
        self.get_time_patcher.stop()
        self.logger_patcher.stop()
        self.sleep_patcher.stop()
        self.wait_patcher.stop()

    def test_successful_reschedule(self):
        """Successful reschedule returns SUCCESS status."""
        from visa import reschedule

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.text = "Your appointment has been Successfully Scheduled"
        mock_response.status_code = 200
        self.mock_requests.post.return_value = mock_response

        result = reschedule("2026-07-15")

        self.assertEqual(result[0], "SUCCESS")
        self.assertIn("2026-07-15", result[1])
        self.assertIn("09:00", result[1])

    def test_success_detection_case_insensitive(self):
        """Success detection should be case-insensitive."""
        from visa import reschedule

        # Test various case combinations
        test_cases = [
            "successfully scheduled",
            "SUCCESSFULLY SCHEDULED",
            "Successfully Scheduled",
            "Your appointment was successfully scheduled for tomorrow",
        ]

        for response_text in test_cases:
            mock_response = MagicMock()
            mock_response.text = response_text
            mock_response.status_code = 200
            self.mock_requests.post.return_value = mock_response

            result = reschedule("2026-07-15")

            self.assertEqual(result[0], "SUCCESS", f"Failed for: {response_text}")


class TestRescheduleNoSlots(unittest.TestCase):
    """Test NO_SLOTS scenarios (race condition)."""

    def setUp(self):
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        self.get_time_patcher = patch('visa.get_time_with_retry')
        self.mock_get_time = self.get_time_patcher.start()

        self.logger_patcher = patch('visa.get_logger')
        self.mock_logger = self.logger_patcher.start()
        self.mock_logger.return_value = MagicMock()

    def tearDown(self):
        self.driver_patcher.stop()
        self.get_time_patcher.stop()
        self.logger_patcher.stop()

    def test_no_time_slots_returns_no_slots(self):
        """When get_time_with_retry returns None, should return NO_SLOTS."""
        from visa import reschedule

        self.mock_get_time.return_value = None

        result = reschedule("2026-07-15")

        self.assertEqual(result[0], "NO_SLOTS")
        self.assertIn("No time slots", result[1])


class TestRescheduleSessionErrors(unittest.TestCase):
    """Test session-related error scenarios."""

    def setUp(self):
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        self.get_time_patcher = patch('visa.get_time_with_retry')
        self.mock_get_time = self.get_time_patcher.start()
        self.mock_get_time.return_value = "09:00"

        self.logger_patcher = patch('visa.get_logger')
        self.mock_logger = self.logger_patcher.start()
        self.mock_logger.return_value = MagicMock()

        self.sleep_patcher = patch('visa.time.sleep')
        self.mock_sleep = self.sleep_patcher.start()

        self.wait_patcher = patch('visa.Wait')
        self.mock_wait = self.wait_patcher.start()

    def tearDown(self):
        self.driver_patcher.stop()
        self.get_time_patcher.stop()
        self.logger_patcher.stop()
        self.sleep_patcher.stop()
        self.wait_patcher.stop()

    def test_missing_session_cookie(self):
        """Missing session cookie should return FAIL."""
        from visa import reschedule

        self.mock_driver.get_cookie.return_value = None

        result = reschedule("2026-07-15")

        self.assertEqual(result[0], "FAIL")
        self.assertIn("Session cookie not found", result[1])

    def test_missing_authenticity_token(self):
        """Missing authenticity token should return FAIL."""
        from visa import reschedule

        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.return_value = "Mozilla/5.0..."

        # Raise exception when trying to find authenticity token
        from selenium.common.exceptions import NoSuchElementException
        self.mock_driver.find_element.side_effect = NoSuchElementException("Element not found")

        result = reschedule("2026-07-15")

        self.assertEqual(result[0], "FAIL")
        self.assertIn("authenticity token", result[1].lower())


class TestRescheduleNetworkErrors(unittest.TestCase):
    """Test network error scenarios."""

    def setUp(self):
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        self.requests_patcher = patch('visa.requests')
        self.mock_requests = self.requests_patcher.start()

        self.get_time_patcher = patch('visa.get_time_with_retry')
        self.mock_get_time = self.get_time_patcher.start()
        self.mock_get_time.return_value = "09:00"

        self.logger_patcher = patch('visa.get_logger')
        self.mock_logger = self.logger_patcher.start()
        self.mock_logger.return_value = MagicMock()

        self.sleep_patcher = patch('visa.time.sleep')
        self.mock_sleep = self.sleep_patcher.start()

        self.wait_patcher = patch('visa.Wait')
        self.mock_wait = self.wait_patcher.start()

        # Configure default mocks
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.return_value = "Mozilla/5.0..."

        mock_token_element = MagicMock()
        mock_token_element.get_attribute.return_value = "test_auth_token"
        self.mock_driver.find_element.return_value = mock_token_element

    def tearDown(self):
        self.driver_patcher.stop()
        self.requests_patcher.stop()
        self.get_time_patcher.stop()
        self.logger_patcher.stop()
        self.sleep_patcher.stop()
        self.wait_patcher.stop()

    def test_request_timeout(self):
        """Request timeout should return FAIL with timeout message."""
        from visa import reschedule
        import requests

        self.mock_requests.post.side_effect = requests.exceptions.Timeout("Connection timed out")
        self.mock_requests.exceptions = requests.exceptions

        result = reschedule("2026-07-15")

        self.assertEqual(result[0], "FAIL")
        self.assertIn("timed out", result[1].lower())

    def test_network_error(self):
        """Network error should return FAIL."""
        from visa import reschedule
        import requests

        self.mock_requests.post.side_effect = requests.exceptions.ConnectionError("Network unreachable")
        self.mock_requests.exceptions = requests.exceptions

        result = reschedule("2026-07-15")

        self.assertEqual(result[0], "FAIL")
        self.assertIn("Network error", result[1])


class TestRescheduleFailedResponses(unittest.TestCase):
    """Test failed booking response scenarios."""

    def setUp(self):
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        self.requests_patcher = patch('visa.requests')
        self.mock_requests = self.requests_patcher.start()

        self.get_time_patcher = patch('visa.get_time_with_retry')
        self.mock_get_time = self.get_time_patcher.start()
        self.mock_get_time.return_value = "09:00"

        self.logger_patcher = patch('visa.get_logger')
        self.mock_logger = self.logger_patcher.start()
        self.mock_logger.return_value = MagicMock()

        self.sleep_patcher = patch('visa.time.sleep')
        self.mock_sleep = self.sleep_patcher.start()

        self.wait_patcher = patch('visa.Wait')
        self.mock_wait = self.wait_patcher.start()

        # Configure default mocks
        self.mock_driver.get_cookie.return_value = {"value": "test_session"}
        self.mock_driver.execute_script.return_value = "Mozilla/5.0..."

        mock_token_element = MagicMock()
        mock_token_element.get_attribute.return_value = "test_auth_token"
        self.mock_driver.find_element.return_value = mock_token_element

    def tearDown(self):
        self.driver_patcher.stop()
        self.requests_patcher.stop()
        self.get_time_patcher.stop()
        self.logger_patcher.stop()
        self.sleep_patcher.stop()
        self.wait_patcher.stop()

    def test_http_500_error(self):
        """HTTP 500 response should return FAIL."""
        from visa import reschedule

        mock_response = MagicMock()
        mock_response.text = "Internal Server Error"
        mock_response.status_code = 500
        self.mock_requests.post.return_value = mock_response

        result = reschedule("2026-07-15")

        self.assertEqual(result[0], "FAIL")
        self.assertIn("500", result[1])

    def test_booking_rejected_response(self):
        """Booking rejected response should return FAIL."""
        from visa import reschedule

        mock_response = MagicMock()
        mock_response.text = "Sorry, this appointment slot is no longer available"
        mock_response.status_code = 200
        self.mock_requests.post.return_value = mock_response

        result = reschedule("2026-07-15")

        self.assertEqual(result[0], "FAIL")

    def test_html_error_page(self):
        """HTML error page response should return FAIL."""
        from visa import reschedule

        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <head><title>Error</title></head>
        <body><h1>An error occurred</h1></body>
        </html>
        """
        mock_response.status_code = 200
        self.mock_requests.post.return_value = mock_response

        result = reschedule("2026-07-15")

        self.assertEqual(result[0], "FAIL")


class TestRescheduleFormData(unittest.TestCase):
    """Test that correct form data is submitted."""

    def setUp(self):
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        self.requests_patcher = patch('visa.requests')
        self.mock_requests = self.requests_patcher.start()

        self.get_time_patcher = patch('visa.get_time_with_retry')
        self.mock_get_time = self.get_time_patcher.start()
        self.mock_get_time.return_value = "10:30"

        self.logger_patcher = patch('visa.get_logger')
        self.mock_logger = self.logger_patcher.start()
        self.mock_logger.return_value = MagicMock()

        self.sleep_patcher = patch('visa.time.sleep')
        self.mock_sleep = self.sleep_patcher.start()

        self.wait_patcher = patch('visa.Wait')
        self.mock_wait = self.wait_patcher.start()

        self.facility_patcher = patch('visa.FACILITY_ID', 94)
        self.mock_facility = self.facility_patcher.start()

        # Configure default mocks
        self.mock_driver.get_cookie.return_value = {"value": "test_session_123"}
        self.mock_driver.execute_script.return_value = "Mozilla/5.0..."

        mock_token_element = MagicMock()
        mock_token_element.get_attribute.return_value = "csrf_token_abc"
        self.mock_driver.find_element.return_value = mock_token_element

        # Successful response
        mock_response = MagicMock()
        mock_response.text = "successfully scheduled"
        mock_response.status_code = 200
        self.mock_requests.post.return_value = mock_response

    def tearDown(self):
        self.driver_patcher.stop()
        self.requests_patcher.stop()
        self.get_time_patcher.stop()
        self.logger_patcher.stop()
        self.sleep_patcher.stop()
        self.wait_patcher.stop()
        self.facility_patcher.stop()

    def test_correct_form_data_submitted(self):
        """Verify correct form data is submitted to API."""
        from visa import reschedule

        reschedule("2026-07-15")

        # Check POST was called
        self.mock_requests.post.assert_called_once()

        # Get the data argument
        call_args = self.mock_requests.post.call_args
        data = call_args[1]['data']

        # Verify required fields
        self.assertEqual(data['appointments[consulate_appointment][date]'], "2026-07-15")
        self.assertEqual(data['appointments[consulate_appointment][time]'], "10:30")
        self.assertEqual(data['authenticity_token'], "csrf_token_abc")

    def test_timeout_parameter_passed(self):
        """Verify timeout parameter is passed to requests.post."""
        from visa import reschedule

        reschedule("2026-07-15")

        call_args = self.mock_requests.post.call_args
        self.assertEqual(call_args[1]['timeout'], 30)


class TestGetTimeWithRetry(unittest.TestCase):
    """Test get_time_with_retry function."""

    def setUp(self):
        self.driver_patcher = patch('visa.driver')
        self.mock_driver = self.driver_patcher.start()

        self.logger_patcher = patch('visa.get_logger')
        self.mock_logger = self.logger_patcher.start()
        self.mock_logger.return_value = MagicMock()

        self.relogin_patcher = patch('visa.relogin')
        self.mock_relogin = self.relogin_patcher.start()

    def tearDown(self):
        self.driver_patcher.stop()
        self.logger_patcher.stop()
        self.relogin_patcher.stop()

    def test_returns_first_available_time(self):
        """Should return the first (earliest) available time."""
        from visa import get_time_with_retry

        self.mock_driver.get_cookie.return_value = {"value": "session123"}
        self.mock_driver.execute_script.return_value = '{"available_times": ["09:00", "10:00", "11:00"]}'

        result = get_time_with_retry("2026-07-15")

        self.assertEqual(result, "09:00")

    def test_returns_none_when_no_slots(self):
        """Should return None when no time slots available."""
        from visa import get_time_with_retry

        self.mock_driver.get_cookie.return_value = {"value": "session123"}
        self.mock_driver.execute_script.return_value = '{"available_times": []}'

        result = get_time_with_retry("2026-07-15")

        self.assertIsNone(result)

    def test_returns_none_when_available_times_null(self):
        """Should return None when available_times is null."""
        from visa import get_time_with_retry

        self.mock_driver.get_cookie.return_value = {"value": "session123"}
        self.mock_driver.execute_script.return_value = '{"available_times": null}'

        result = get_time_with_retry("2026-07-15")

        self.assertIsNone(result)

    def test_session_cookie_missing_raises(self):
        """Should raise when session cookie is missing."""
        from visa import get_time_with_retry

        self.mock_driver.get_cookie.return_value = None

        with self.assertRaises(ValueError) as context:
            get_time_with_retry("2026-07-15")

        self.assertIn("Session cookie not found", str(context.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)
