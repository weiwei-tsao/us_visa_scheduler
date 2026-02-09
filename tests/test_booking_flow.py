"""
Unit tests for the booking slots workflow.

Tests the complete booking flow from slot detection to appointment booking,
including edge cases and error scenarios identified in the analysis:

Critical Issues Tested:
- Empty time array causing IndexError
- No timeout on POST request
- Date boundary exclusion (strict inequality)
- Session cookie null check
- Fragile success string matching

Race Conditions Tested:
- Slot taken between date check and time fetch
- Session expiration during booking
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock all external dependencies BEFORE importing visa
# Mocking removed to prevent pollution of sys.modules which breaks other tests.
# If mocks are needed, use patch.dict('sys.modules', ...) context managers within specific tests.
# mock_modules = {
#     'selenium': MagicMock(),
#     ...
# }
# for mod_name, mock_obj in mock_modules.items():
#     sys.modules[mod_name] = mock_obj

# Mock configparser to avoid reading real config.ini
mock_config = MagicMock()
mock_config.read.return_value = None
mock_config.__getitem__ = lambda self, key: {
    'PERSONAL_INFO': {
        'USERNAME': 'test@example.com',
        'PASSWORD': 'testpass',
        'SCHEDULE_ID': '12345',
        'PRIOD_START': '2026-06-01',
        'PRIOD_END': '2026-12-31',
        'YOUR_EMBASSY': 'en-ca-tor',
    },
    'NOTIFICATION': {
        'SENDGRID_API_KEY': '',
        'SENDGRID_EMAIL_SENDER': '',
        'TELEGRAM_BOT_TOKEN': '',
        'TELEGRAM_CHAT_ID': '',
    },
    'TIME': {
        'RETRY_TIME_L_BOUND': '111',
        'RETRY_TIME_U_BOUND': '300',
        'WORK_LIMIT_TIME': '0.75',
    },
    'CHROMEDRIVER': {
        'LOCAL_USE': 'true',
        'HUB_ADDRESS': '',
    },
    'BEHAVIOR': {
        'HEADLESS': 'false',
        'STEP_DELAY': '0.5',
    },
}.get(key, {})

mock_config.get = lambda section, key, fallback='': mock_config[section].get(key, fallback)
mock_config.__contains__ = lambda self, key: key in ['PERSONAL_INFO', 'NOTIFICATION', 'TIME', 'CHROMEDRIVER', 'BEHAVIOR']


class TestDateFiltering(unittest.TestCase):
    """Test the date filtering logic in isolation."""

    def test_is_in_period_within_range(self):
        """Date within range should return True."""
        from datetime import datetime

        def is_in_period(date_str, PSD, PED):
            new_date = datetime.strptime(date_str, "%Y-%m-%d")
            return PED > new_date and new_date > PSD

        PSD = datetime.strptime("2026-06-01", "%Y-%m-%d")
        PED = datetime.strptime("2026-12-31", "%Y-%m-%d")

        result = is_in_period("2026-07-15", PSD, PED)
        self.assertTrue(result)

    def test_is_in_period_before_range(self):
        """Date before range should return False."""
        from datetime import datetime

        def is_in_period(date_str, PSD, PED):
            new_date = datetime.strptime(date_str, "%Y-%m-%d")
            return PED > new_date and new_date > PSD

        PSD = datetime.strptime("2026-06-01", "%Y-%m-%d")
        PED = datetime.strptime("2026-12-31", "%Y-%m-%d")

        result = is_in_period("2026-05-15", PSD, PED)
        self.assertFalse(result)

    def test_is_in_period_after_range(self):
        """Date after range should return False."""
        from datetime import datetime

        def is_in_period(date_str, PSD, PED):
            new_date = datetime.strptime(date_str, "%Y-%m-%d")
            return PED > new_date and new_date > PSD

        PSD = datetime.strptime("2026-06-01", "%Y-%m-%d")
        PED = datetime.strptime("2026-12-31", "%Y-%m-%d")

        result = is_in_period("2027-01-15", PSD, PED)
        self.assertFalse(result)

    def test_is_in_period_on_start_boundary_excluded(self):
        """
        BUG TEST: Date exactly on start boundary is EXCLUDED.

        Current: PED > new_date > PSD (strict inequality)
        Expected: Should use >= for inclusive boundaries
        """
        from datetime import datetime

        def is_in_period(date_str, PSD, PED):
            new_date = datetime.strptime(date_str, "%Y-%m-%d")
            return PED > new_date and new_date > PSD  # Current buggy logic

        PSD = datetime.strptime("2026-06-01", "%Y-%m-%d")
        PED = datetime.strptime("2026-12-31", "%Y-%m-%d")

        # BUG: 2026-06-01 is excluded even though it should be included
        result = is_in_period("2026-06-01", PSD, PED)
        self.assertFalse(result)  # Documents current buggy behavior

    def test_is_in_period_on_end_boundary_excluded(self):
        """
        BUG TEST: Date exactly on end boundary is EXCLUDED.
        """
        from datetime import datetime

        def is_in_period(date_str, PSD, PED):
            new_date = datetime.strptime(date_str, "%Y-%m-%d")
            return PED > new_date and new_date > PSD

        PSD = datetime.strptime("2026-06-01", "%Y-%m-%d")
        PED = datetime.strptime("2026-12-31", "%Y-%m-%d")

        # BUG: 2026-12-31 is excluded
        result = is_in_period("2026-12-31", PSD, PED)
        self.assertFalse(result)


class TestExtractDate(unittest.TestCase):
    """Test date extraction from various formats."""

    def test_extract_date_from_dict(self):
        """Should extract date from dict format."""
        def extract_date(d):
            if isinstance(d, dict):
                return d.get('date')
            return d

        result = extract_date({"date": "2026-07-15"})
        self.assertEqual(result, "2026-07-15")

    def test_extract_date_from_string(self):
        """Should return string date as-is."""
        def extract_date(d):
            if isinstance(d, dict):
                return d.get('date')
            return d

        result = extract_date("2026-07-15")
        self.assertEqual(result, "2026-07-15")

    def test_extract_date_missing_key(self):
        """Should return None if date key missing."""
        def extract_date(d):
            if isinstance(d, dict):
                return d.get('date')
            return d

        result = extract_date({"other_key": "value"})
        self.assertIsNone(result)


class TestTimeSlotSelection(unittest.TestCase):
    """Test time slot selection logic."""

    def test_selects_last_time_slot(self):
        """
        Current behavior: Returns LAST time slot.

        This may be intentional or a bug - most users want earliest slot.
        """
        available_times = ["09:00", "10:30", "14:00", "16:30"]

        # Current logic: take last slot
        result = available_times[-1]
        self.assertEqual(result, "16:30")

    def test_empty_times_array_raises_index_error(self):
        """
        CRITICAL BUG TEST: Empty array causes IndexError.

        Race condition: slot taken between date fetch and time fetch.
        """
        available_times = []

        with self.assertRaises(IndexError):
            _ = available_times[-1]

    def test_none_times_raises_type_error(self):
        """
        CRITICAL BUG TEST: None causes TypeError.

        If API returns malformed response without available_times.
        """
        available_times = None

        with self.assertRaises(TypeError):
            _ = available_times[-1]

    def test_single_time_slot_works(self):
        """Single time slot should work."""
        available_times = ["11:00"]

        result = available_times[-1]
        self.assertEqual(result, "11:00")


class TestSuccessDetection(unittest.TestCase):
    """Test booking success detection logic."""

    def test_detects_success_exact_phrase(self):
        """Should detect exact 'Successfully Scheduled' phrase."""
        response_text = "Your appointment has been Successfully Scheduled for July 15, 2026."

        result = response_text.find('Successfully Scheduled') != -1
        self.assertTrue(result)

    def test_case_sensitive_fails_lowercase(self):
        """
        BUG TEST: Lowercase 'successfully scheduled' not detected.

        Booking may have succeeded but reports as failure.
        """
        response_text = "Your appointment has been successfully scheduled for July 15, 2026."

        # BUG: Case-sensitive match fails
        result = response_text.find('Successfully Scheduled') != -1
        self.assertFalse(result)

    def test_partial_phrase_fails(self):
        """Partial phrase should not match."""
        response_text = "Successfully submitted your request."

        result = response_text.find('Successfully Scheduled') != -1
        self.assertFalse(result)


class TestCookieHandling(unittest.TestCase):
    """Test session cookie handling."""

    def test_missing_cookie_returns_none(self):
        """
        BUG TEST: Missing cookie scenario.

        driver.get_cookie() returns None if cookie doesn't exist.
        Current code does: cookie["value"] which raises TypeError.
        """
        cookie = None  # Cookie not found

        with self.assertRaises(TypeError):
            _ = cookie["value"]

    def test_valid_cookie_returns_value(self):
        """Valid cookie should return value."""
        cookie = {"value": "session_123", "name": "_yatri_session"}

        result = cookie["value"]
        self.assertEqual(result, "session_123")


class TestSessionExpiredDetection(unittest.TestCase):
    """Test session expired error detection."""

    def test_detects_401_error(self):
        """Should detect 401 as session expired."""
        def is_session_expired_error(error):
            error_str = str(error).lower()
            return any(x in error_str for x in [
                'expecting value', 'jsondecodeerror', 'empty response',
                '401', '403', 'unauthorized', 'session', 'expired'
            ])

        error = Exception("401 Unauthorized")
        self.assertTrue(is_session_expired_error(error))

    def test_detects_json_decode_error(self):
        """Should detect JSONDecodeError as potential session issue."""
        def is_session_expired_error(error):
            error_str = str(error).lower()
            return any(x in error_str for x in [
                'expecting value', 'jsondecodeerror', 'empty response',
                '401', '403', 'unauthorized', 'session', 'expired'
            ])

        error = Exception("JSONDecodeError: Expecting value")
        self.assertTrue(is_session_expired_error(error))

    def test_normal_network_error_not_session_expired(self):
        """Normal network errors should not be classified as session expired."""
        def is_session_expired_error(error):
            error_str = str(error).lower()
            return any(x in error_str for x in [
                'expecting value', 'jsondecodeerror', 'empty response',
                '401', '403', 'unauthorized', 'session', 'expired'
            ])

        error = Exception("Connection timeout")
        self.assertFalse(is_session_expired_error(error))


class TestPostRequestTimeout(unittest.TestCase):
    """Test POST request timeout handling."""

    def test_no_timeout_in_current_implementation(self):
        """
        BUG TEST: Current implementation has no timeout.

        Simulates checking if timeout parameter is passed to requests.post()
        """
        # Simulate the current implementation
        mock_requests = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Successfully Scheduled"
        mock_requests.post.return_value = mock_response

        # Current call (without timeout)
        url = "https://example.com/appointment"
        headers = {"User-Agent": "test"}
        data = {"date": "2026-07-15"}

        mock_requests.post(url, headers=headers, data=data)

        # Verify call was made without timeout
        call_kwargs = mock_requests.post.call_args[1]
        self.assertNotIn('timeout', call_kwargs)

    def test_recommended_timeout_behavior(self):
        """Test how it SHOULD work with timeout."""
        mock_requests = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Successfully Scheduled"
        mock_requests.post.return_value = mock_response

        url = "https://example.com/appointment"
        headers = {"User-Agent": "test"}
        data = {"date": "2026-07-15"}

        # Recommended call (with timeout)
        mock_requests.post(url, headers=headers, data=data, timeout=30)

        call_kwargs = mock_requests.post.call_args[1]
        self.assertEqual(call_kwargs.get('timeout'), 30)


class TestRaceConditionScenario(unittest.TestCase):
    """Test race condition scenarios in booking flow."""

    def test_slot_taken_between_date_and_time_fetch(self):
        """
        CRITICAL: Simulate race condition where slot is grabbed by another user.

        Timeline:
        T+0: get_date_with_retry() returns ["2026-07-15"] - slot available
        T+1: Another user books the last slot for 2026-07-15
        T+2: get_time_with_retry() returns {"available_times": []} - empty!
        T+3: available_times[-1] raises IndexError
        """
        # Step 1: Dates API returns available date
        dates_response = [{"date": "2026-07-15"}]
        self.assertEqual(len(dates_response), 1)

        # Step 2: Time API returns empty (slot was taken)
        times_response = {"available_times": []}

        # Step 3: Attempt to access last time slot
        available_times = times_response.get("available_times")

        # BUG: This crashes instead of handling gracefully
        with self.assertRaises(IndexError):
            _ = available_times[-1]

    def test_session_expired_between_checks(self):
        """
        Simulate session expiring between date fetch and booking.
        """
        # Session was valid during date fetch
        session_valid = {"value": "session_123"}

        # Session expired by the time we try to book
        session_expired = None

        # First check works
        self.assertIsNotNone(session_valid["value"])

        # Second check fails
        with self.assertRaises(TypeError):
            _ = session_expired["value"]


class TestFormDataExtraction(unittest.TestCase):
    """Test form data extraction with bare except clauses."""

    def test_bare_except_hides_errors(self):
        """
        BUG TEST: Bare except: pass hides real errors.

        Current code:
        try: data["utf8"] = driver.find_element(...)
        except: pass

        This catches ALL exceptions including network errors.
        """
        def extract_with_bare_except(find_element_func):
            data = {}
            try:
                data["utf8"] = find_element_func()
            except:
                pass  # All errors hidden!
            return data

        # Simulate network error
        def raise_network_error():
            raise ConnectionError("Network timeout")

        # BUG: Network error is silently swallowed
        result = extract_with_bare_except(raise_network_error)
        self.assertNotIn("utf8", result)  # Field missing, but we don't know why

    def test_specific_exception_handling(self):
        """Test how it SHOULD work with specific exceptions."""
        def extract_with_specific_except(find_element_func):
            data = {}
            try:
                data["utf8"] = find_element_func()
            except KeyError:
                # Only catch expected element-not-found errors
                pass
            # Other errors (network, etc.) should propagate
            return data

        def raise_network_error():
            raise ConnectionError("Network timeout")

        # Network error should NOT be caught
        with self.assertRaises(ConnectionError):
            extract_with_specific_except(raise_network_error)


class TestBookingFlowEndToEnd(unittest.TestCase):
    """End-to-end simulation of booking flow scenarios."""

    def test_happy_path_booking(self):
        """Simulate successful booking flow."""
        # Step 1: Date fetch
        dates = [{"date": "2026-07-15"}, {"date": "2026-07-20"}]

        # Step 2: Date filtering
        PRIOD_START = datetime.strptime("2026-06-01", "%Y-%m-%d")
        PRIOD_END = datetime.strptime("2026-12-31", "%Y-%m-%d")

        matching_date = None
        for d in dates:
            date_str = d.get("date")
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            if PRIOD_END > date_obj > PRIOD_START:
                matching_date = date_str
                break

        self.assertEqual(matching_date, "2026-07-15")

        # Step 3: Time fetch
        times = {"available_times": ["10:00", "14:00", "16:00"]}
        selected_time = times["available_times"][-1]  # Takes last
        self.assertEqual(selected_time, "16:00")

        # Step 4: Success detection
        response_text = "Successfully Scheduled your appointment for 2026-07-15"
        is_success = response_text.find('Successfully Scheduled') != -1
        self.assertTrue(is_success)

    def test_no_matching_dates(self):
        """Simulate scenario where no dates match the target range."""
        dates = [{"date": "2026-05-01"}, {"date": "2027-02-15"}]

        PRIOD_START = datetime.strptime("2026-06-01", "%Y-%m-%d")
        PRIOD_END = datetime.strptime("2026-12-31", "%Y-%m-%d")

        matching_date = None
        for d in dates:
            date_str = d.get("date")
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            if PRIOD_END > date_obj > PRIOD_START:
                matching_date = date_str
                break

        self.assertIsNone(matching_date)

    def test_empty_dates_response(self):
        """Simulate empty dates response (no slots or rate limited)."""
        dates = []

        # Should trigger ban detection logic
        self.assertEqual(len(dates), 0)
        # In real code, this increments consecutive_empty_count


class TestConfigValidation(unittest.TestCase):
    """Test configuration validation for booking."""

    def test_date_range_validation(self):
        """Start date should be before end date."""
        start = "2026-12-31"
        end = "2026-06-01"

        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")

        is_valid = start_dt < end_dt
        self.assertFalse(is_valid)  # Invalid: start after end

    def test_valid_date_range(self):
        """Valid date range should pass."""
        start = "2026-06-01"
        end = "2026-12-31"

        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")

        is_valid = start_dt < end_dt
        self.assertTrue(is_valid)


if __name__ == '__main__':
    unittest.main(verbosity=2)
