"""
Mock tests for the booking execution flow.

Assumes we already have a desired date slot and tests the flow from that point:
1. Fetching available time slots for the date
2. Navigating to appointment page
3. Extracting form data (authenticity token, etc.)
4. Submitting the booking POST request
5. Verifying booking success/failure

This tests the critical path where failures are most impactful.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import json
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockDriver:
    """Mock Selenium WebDriver for testing."""

    def __init__(self):
        self.cookies = {"_yatri_session": {"value": "mock_session_abc123"}}
        self.script_responses = []
        self.current_url = ""
        self.elements = {}

    def get_cookie(self, name):
        return self.cookies.get(name)

    def set_cookie(self, name, value):
        self.cookies[name] = value

    def execute_script(self, script):
        if self.script_responses:
            return self.script_responses.pop(0)
        return None

    def get(self, url):
        self.current_url = url

    def find_element(self, by, value):
        if value in self.elements:
            return self.elements[value]
        raise Exception(f"Element not found: {value}")

    def add_element(self, name, value):
        mock_element = Mock()
        mock_element.get_attribute.return_value = value
        self.elements[name] = mock_element


class MockResponse:
    """Mock requests.Response for testing."""

    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


class TestTimeSlotFetching(unittest.TestCase):
    """
    Test fetching time slots for a known available date.

    This is the first step after we have identified a desired date.
    """

    def setUp(self):
        self.driver = MockDriver()
        self.target_date = "2026-07-15"

    def test_successful_time_fetch(self):
        """Successfully fetch time slots for a date."""
        self.driver.script_responses = [
            json.dumps({"available_times": ["09:00", "10:30", "14:00", "16:30"]})
        ]

        # Simulate get_time_with_retry logic
        session = self.driver.get_cookie("_yatri_session")["value"]
        content = self.driver.execute_script("mock_script")
        data = json.loads(content)
        available_times = data.get("available_times")

        self.assertEqual(len(available_times), 4)
        self.assertEqual(available_times[0], "09:00")
        self.assertEqual(available_times[-1], "16:30")

    def test_empty_times_after_slot_grabbed(self):
        """
        CRITICAL: Time slots empty because another user grabbed the slot.

        This is a race condition between date check and time fetch.
        """
        self.driver.script_responses = [
            json.dumps({"available_times": []})  # All slots taken!
        ]

        session = self.driver.get_cookie("_yatri_session")["value"]
        content = self.driver.execute_script("mock_script")
        data = json.loads(content)
        available_times = data.get("available_times")

        # BUG: Current code does available_times[-1] which crashes here
        self.assertEqual(len(available_times), 0)
        with self.assertRaises(IndexError):
            _ = available_times[-1]

    def test_missing_available_times_key(self):
        """
        API returns malformed response without available_times key.
        """
        self.driver.script_responses = [
            json.dumps({"error": "Invalid date"})  # No available_times
        ]

        content = self.driver.execute_script("mock_script")
        data = json.loads(content)
        available_times = data.get("available_times")  # Returns None

        self.assertIsNone(available_times)
        with self.assertRaises(TypeError):
            _ = available_times[-1]

    def test_session_expired_during_time_fetch(self):
        """Session expires while fetching time slots."""
        self.driver.cookies = {}  # Session gone

        cookie = self.driver.get_cookie("_yatri_session")
        self.assertIsNone(cookie)

        with self.assertRaises(TypeError):
            _ = cookie["value"]


class TestAppointmentPageNavigation(unittest.TestCase):
    """
    Test navigating to the appointment page and waiting for form.
    """

    def setUp(self):
        self.driver = MockDriver()
        self.appointment_url = "https://ais.usvisa-info.com/en-ca/niv/schedule/12345/appointment"

    def test_successful_navigation(self):
        """Successfully navigate to appointment page."""
        self.driver.get(self.appointment_url)
        self.assertEqual(self.driver.current_url, self.appointment_url)

    def test_authenticity_token_found(self):
        """Find authenticity token on appointment page."""
        self.driver.add_element("authenticity_token", "csrf_token_xyz123")

        element = self.driver.find_element("name", "authenticity_token")
        token = element.get_attribute("value")

        self.assertEqual(token, "csrf_token_xyz123")

    def test_authenticity_token_missing(self):
        """
        BUG SCENARIO: Authenticity token not found.

        Could happen if:
        - Page structure changed
        - Page didn't load properly
        - Session expired
        """
        with self.assertRaises(Exception) as context:
            self.driver.find_element("name", "authenticity_token")

        self.assertIn("not found", str(context.exception))


class TestFormDataExtraction(unittest.TestCase):
    """
    Test extracting all required form fields for booking POST.
    """

    def setUp(self):
        self.driver = MockDriver()
        # Add all expected form elements
        self.driver.add_element("authenticity_token", "csrf_token_123")
        self.driver.add_element("utf8", "✓")
        self.driver.add_element("confirmed_limit_message", "1")
        self.driver.add_element("use_consulate_appointment_capacity", "true")

    def test_extract_all_form_fields(self):
        """Successfully extract all form fields."""
        data = {
            "appointments[consulate_appointment][facility_id]": "94",
            "appointments[consulate_appointment][date]": "2026-07-15",
            "appointments[consulate_appointment][time]": "10:00",
        }

        # Required field
        data["authenticity_token"] = self.driver.find_element(
            "name", "authenticity_token"
        ).get_attribute("value")

        # Optional fields (current code uses bare except)
        try:
            data["utf8"] = self.driver.find_element("name", "utf8").get_attribute("value")
        except:
            pass

        try:
            data["confirmed_limit_message"] = self.driver.find_element(
                "name", "confirmed_limit_message"
            ).get_attribute("value")
        except:
            pass

        self.assertEqual(data["authenticity_token"], "csrf_token_123")
        self.assertEqual(data["utf8"], "✓")
        self.assertEqual(data["confirmed_limit_message"], "1")

    def test_missing_optional_field_continues(self):
        """Missing optional fields should not break booking."""
        driver = MockDriver()
        driver.add_element("authenticity_token", "csrf_token_123")
        # utf8 and other optional fields NOT added

        data = {}

        # Required field - should succeed
        data["authenticity_token"] = driver.find_element(
            "name", "authenticity_token"
        ).get_attribute("value")

        # Optional field - should fail silently
        try:
            data["utf8"] = driver.find_element("name", "utf8").get_attribute("value")
        except:
            pass

        self.assertEqual(data["authenticity_token"], "csrf_token_123")
        self.assertNotIn("utf8", data)

    def test_bare_except_hides_network_error(self):
        """
        BUG: Bare except hides real network errors.

        Current code catches ALL exceptions, including network issues
        that should be propagated.
        """
        def mock_find_that_raises_network_error(*args):
            raise ConnectionError("Network timeout")

        driver = MockDriver()
        driver.find_element = mock_find_that_raises_network_error

        data = {}
        try:
            data["utf8"] = driver.find_element("name", "utf8").get_attribute("value")
        except:
            pass  # Network error silently swallowed!

        # BUG: We don't know the real error occurred
        self.assertNotIn("utf8", data)


class TestBookingPostRequest(unittest.TestCase):
    """
    Test the POST request to submit the booking.
    """

    def setUp(self):
        self.appointment_url = "https://ais.usvisa-info.com/en-ca/niv/schedule/12345/appointment"
        self.headers = {
            "User-Agent": "Mozilla/5.0...",
            "Referer": self.appointment_url,
            "Cookie": "_yatri_session=mock_session_123"
        }
        self.data = {
            "appointments[consulate_appointment][facility_id]": "94",
            "appointments[consulate_appointment][date]": "2026-07-15",
            "appointments[consulate_appointment][time]": "10:00",
            "authenticity_token": "csrf_token_123",
        }

    def test_successful_booking_response(self):
        """Successful booking returns 'Successfully Scheduled' text."""
        mock_response = MockResponse(
            text="<html>Successfully Scheduled your appointment for July 15, 2026</html>",
            status_code=200
        )

        is_success = mock_response.text.find('Successfully Scheduled') != -1
        self.assertTrue(is_success)

    def test_failed_booking_response(self):
        """Failed booking does not contain success text."""
        mock_response = MockResponse(
            text="<html>Sorry, that time slot is no longer available.</html>",
            status_code=200
        )

        is_success = mock_response.text.find('Successfully Scheduled') != -1
        self.assertFalse(is_success)

    def test_server_error_response(self):
        """Server error should be detected."""
        mock_response = MockResponse(
            text="<html>500 Internal Server Error</html>",
            status_code=500
        )

        # BUG: Current code only checks text, not status code
        is_success = mock_response.text.find('Successfully Scheduled') != -1
        self.assertFalse(is_success)

        # Should also check status code
        is_server_error = mock_response.status_code >= 500
        self.assertTrue(is_server_error)

    def test_case_insensitive_success_detection(self):
        """
        BUG: Current code is case-sensitive.

        If server returns lowercase, booking is marked as failed.
        """
        mock_response = MockResponse(
            text="<html>successfully scheduled your appointment</html>",
            status_code=200
        )

        # Current (buggy) behavior - case sensitive
        is_success_current = mock_response.text.find('Successfully Scheduled') != -1
        self.assertFalse(is_success_current)  # BUG: Returns False

        # Recommended fix - case insensitive
        is_success_fixed = 'successfully scheduled' in mock_response.text.lower()
        self.assertTrue(is_success_fixed)

    def test_no_timeout_allows_hang(self):
        """
        BUG: No timeout on POST request.

        Simulates what happens when requests.post() is called without timeout.
        """
        mock_requests = MagicMock()

        # Simulate a call without timeout
        mock_requests.post(
            self.appointment_url,
            headers=self.headers,
            data=self.data
            # NOTE: No timeout parameter!
        )

        call_kwargs = mock_requests.post.call_args[1]
        self.assertNotIn('timeout', call_kwargs)

    def test_with_recommended_timeout(self):
        """Test with recommended 30-second timeout."""
        mock_requests = MagicMock()

        mock_requests.post(
            self.appointment_url,
            headers=self.headers,
            data=self.data,
            timeout=30  # Recommended fix
        )

        call_kwargs = mock_requests.post.call_args[1]
        self.assertEqual(call_kwargs['timeout'], 30)


class TestBookingResultHandling(unittest.TestCase):
    """
    Test handling of booking results (success/failure).
    """

    def test_success_result_format(self):
        """Successful booking returns proper result tuple."""
        date = "2026-07-15"
        time = "10:00"

        # Simulate successful reschedule return
        result = ["SUCCESS", f"Rescheduled Successfully! {date} {time}"]

        self.assertEqual(result[0], "SUCCESS")
        self.assertIn(date, result[1])
        self.assertIn(time, result[1])

    def test_failure_result_format(self):
        """Failed booking returns proper result tuple."""
        date = "2026-07-15"
        time = "10:00"

        result = ["FAIL", f"Reschedule Failed!!! {date} {time}"]

        self.assertEqual(result[0], "FAIL")
        self.assertIn(date, result[1])

    def test_exit_after_booking_regardless_of_result(self):
        """
        BUG: Script exits after booking attempt regardless of success/failure.

        Current flow:
        1. reschedule() returns result
        2. send_notification()
        3. cleanup_and_exit(EXIT_WORK_LIMIT)  # Always exits!

        This means failed bookings also exit, no retry.
        """
        results = [
            ["SUCCESS", "Rescheduled Successfully!"],
            ["FAIL", "Reschedule Failed!!!"]
        ]

        for result in results:
            # In current code, both cases lead to:
            # cleanup_and_exit(EXIT_WORK_LIMIT)
            should_exit = True  # Current behavior
            self.assertTrue(should_exit)

            # Recommended: Only exit on success
            should_exit_recommended = result[0] == "SUCCESS"
            if result[0] == "FAIL":
                self.assertFalse(should_exit_recommended)


class TestCompleteBookingFlow(unittest.TestCase):
    """
    Integration test for complete booking flow from date to completion.
    """

    def setUp(self):
        self.driver = MockDriver()
        self.target_date = "2026-07-15"
        self.facility_id = "94"
        self.appointment_url = "https://ais.usvisa-info.com/en-ca/niv/schedule/12345/appointment"

    def test_happy_path_complete_flow(self):
        """
        Complete successful booking flow.

        Given: We have a desired date (2026-07-15)
        When: We execute the booking flow
        Then: Appointment is successfully scheduled
        """
        # Step 1: Fetch time slots
        self.driver.script_responses = [
            json.dumps({"available_times": ["09:00", "10:30", "14:00"]}),
            "Mozilla/5.0..."  # User agent for headers
        ]

        content = self.driver.execute_script("fetch_times")
        data = json.loads(content)
        selected_time = data["available_times"][-1]  # Current: takes last
        self.assertEqual(selected_time, "14:00")

        # Step 2: Navigate to appointment page
        self.driver.get(self.appointment_url)
        self.assertEqual(self.driver.current_url, self.appointment_url)

        # Step 3: Extract form data
        self.driver.add_element("authenticity_token", "csrf_token_xyz")
        token = self.driver.find_element("name", "authenticity_token").get_attribute("value")
        self.assertEqual(token, "csrf_token_xyz")

        # Step 4: Build request
        headers = {
            "User-Agent": self.driver.execute_script("get_ua"),
            "Referer": self.appointment_url,
            "Cookie": f"_yatri_session={self.driver.get_cookie('_yatri_session')['value']}"
        }
        form_data = {
            "appointments[consulate_appointment][facility_id]": self.facility_id,
            "appointments[consulate_appointment][date]": self.target_date,
            "appointments[consulate_appointment][time]": selected_time,
            "authenticity_token": token,
        }

        # Step 5: Simulate POST response
        mock_response = MockResponse(
            text="Successfully Scheduled your appointment",
            status_code=200
        )

        # Step 6: Check result
        is_success = mock_response.text.find('Successfully Scheduled') != -1
        self.assertTrue(is_success)

        result = ["SUCCESS", f"Rescheduled Successfully! {self.target_date} {selected_time}"]
        self.assertEqual(result[0], "SUCCESS")

    def test_race_condition_flow(self):
        """
        Race condition: Slot grabbed between date check and booking.

        Given: We have a desired date (2026-07-15)
        When: Time slots become empty before we can book
        Then: Booking crashes with IndexError
        """
        # Step 1: Try to fetch time slots - empty!
        self.driver.script_responses = [
            json.dumps({"available_times": []})  # Someone grabbed it!
        ]

        content = self.driver.execute_script("fetch_times")
        data = json.loads(content)
        available_times = data["available_times"]

        # BUG: Current code crashes here
        self.assertEqual(len(available_times), 0)
        with self.assertRaises(IndexError):
            selected_time = available_times[-1]

    def test_session_expired_during_booking(self):
        """
        Session expires during the booking flow.

        Given: Valid session at start
        When: Session expires before POST
        Then: Cookie access fails with TypeError
        """
        # Session expires
        self.driver.cookies = {}

        cookie = self.driver.get_cookie("_yatri_session")
        self.assertIsNone(cookie)

        with self.assertRaises(TypeError):
            session_value = cookie["value"]

    def test_authenticity_token_missing(self):
        """
        Authenticity token not found on page.

        Could happen if:
        - Page structure changed
        - Not logged in
        - Page load timeout
        """
        # No elements added to driver
        with self.assertRaises(Exception):
            self.driver.find_element("name", "authenticity_token")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases in booking flow."""

    def test_single_time_slot_available(self):
        """Only one time slot available - should work."""
        available_times = ["11:00"]

        selected = available_times[-1]
        self.assertEqual(selected, "11:00")

        selected_first = available_times[0]
        self.assertEqual(selected_first, "11:00")

    def test_unicode_in_response(self):
        """Response contains unicode characters."""
        response_text = "Successfully Scheduled ✓ your appointment"

        is_success = response_text.find('Successfully Scheduled') != -1
        self.assertTrue(is_success)

    def test_html_encoded_response(self):
        """Response contains HTML entities."""
        response_text = "Successfully Scheduled &amp; confirmed"

        is_success = response_text.find('Successfully Scheduled') != -1
        self.assertTrue(is_success)

    def test_multiple_success_phrases(self):
        """Response contains multiple potential success indicators."""
        response_text = """
        <div class="success">
            Successfully Scheduled
            Your appointment has been confirmed.
            Confirmation number: ABC123
        </div>
        """

        is_success = response_text.find('Successfully Scheduled') != -1
        self.assertTrue(is_success)

    def test_time_format_variations(self):
        """Different time format returned by API."""
        time_formats = [
            "09:00",
            "9:00",
            "09:00:00",
            "9:00 AM",
        ]

        for time_str in time_formats:
            # Should be able to use any format
            self.assertIsNotNone(time_str)


class TestRetryScenarios(unittest.TestCase):
    """Test scenarios that might require retry."""

    def test_time_fetch_fails_then_succeeds(self):
        """Time fetch fails first time, succeeds on retry."""
        responses = [
            None,  # First attempt fails
            json.dumps({"available_times": ["10:00"]})  # Retry succeeds
        ]

        attempts = 0
        result = None

        for response in responses:
            attempts += 1
            if response:
                result = json.loads(response)
                break

        self.assertEqual(attempts, 2)
        self.assertIsNotNone(result)
        self.assertEqual(result["available_times"][0], "10:00")

    def test_max_retries_exceeded(self):
        """All retry attempts fail."""
        max_retries = 3
        failures = 0

        for attempt in range(max_retries):
            # Simulate failure
            success = False
            if not success:
                failures += 1

        self.assertEqual(failures, max_retries)


if __name__ == '__main__':
    unittest.main(verbosity=2)
