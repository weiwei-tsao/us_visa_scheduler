"""
Unit tests for date filtering functionality (get_available_date).

Tests the date range filtering logic that determines if available dates
fall within the user's configured target period (PRIOD_START to PRIOD_END).

Key scenarios tested:
1. Date within range - should be selected
2. Date outside range - should be skipped
3. Boundary conditions - start and end dates inclusive
4. Empty date list - should return None
5. Multiple dates - should return first matching date
6. Different date formats (dict vs string)
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGetAvailableDate(unittest.TestCase):
    """Test the get_available_date function."""

    def setUp(self):
        """Set up test fixtures with mocked config values."""
        # Mock the module-level config variables
        self.priod_start_patcher = patch('visa.PRIOD_START', '2026-06-01')
        self.priod_end_patcher = patch('visa.PRIOD_END', '2026-12-31')
        self.logger_patcher = patch('visa.get_logger')

        self.mock_priod_start = self.priod_start_patcher.start()
        self.mock_priod_end = self.priod_end_patcher.start()
        self.mock_logger = self.logger_patcher.start()
        self.mock_logger.return_value = MagicMock()

    def tearDown(self):
        """Clean up patches."""
        self.priod_start_patcher.stop()
        self.priod_end_patcher.stop()
        self.logger_patcher.stop()

    def test_date_within_range_dict_format(self):
        """Date within range (dict format) should be returned."""
        from visa import get_available_date

        dates = [
            {"date": "2026-07-15"},
            {"date": "2026-08-20"},
        ]

        result = get_available_date(dates)

        self.assertEqual(result, "2026-07-15")

    def test_date_within_range_string_format(self):
        """Date within range (string format) should be returned."""
        from visa import get_available_date

        dates = ["2026-07-15", "2026-08-20"]

        result = get_available_date(dates)

        self.assertEqual(result, "2026-07-15")

    def test_date_before_range(self):
        """Date before PRIOD_START should be skipped."""
        from visa import get_available_date

        dates = [
            {"date": "2026-05-15"},  # Before start (2026-06-01)
            {"date": "2026-07-15"},  # Within range
        ]

        result = get_available_date(dates)

        self.assertEqual(result, "2026-07-15")

    def test_date_after_range(self):
        """Date after PRIOD_END should be skipped."""
        from visa import get_available_date

        dates = [
            {"date": "2027-01-15"},  # After end (2026-12-31)
            {"date": "2027-02-15"},  # Also after end
        ]

        result = get_available_date(dates)

        self.assertIsNone(result)

    def test_empty_date_list(self):
        """Empty date list should return None."""
        from visa import get_available_date

        dates = []

        result = get_available_date(dates)

        self.assertIsNone(result)

    def test_boundary_start_date_inclusive(self):
        """PRIOD_START date should be included (>= not >)."""
        from visa import get_available_date

        dates = [{"date": "2026-06-01"}]  # Exactly PRIOD_START

        result = get_available_date(dates)

        self.assertEqual(result, "2026-06-01")

    def test_boundary_end_date_inclusive(self):
        """PRIOD_END date should be included (<= not <)."""
        from visa import get_available_date

        dates = [{"date": "2026-12-31"}]  # Exactly PRIOD_END

        result = get_available_date(dates)

        self.assertEqual(result, "2026-12-31")

    def test_first_matching_date_returned(self):
        """Should return the first date that matches, not necessarily earliest."""
        from visa import get_available_date

        dates = [
            {"date": "2026-05-15"},  # Before range
            {"date": "2026-07-20"},  # First in range
            {"date": "2026-07-15"},  # Also in range but listed later
        ]

        result = get_available_date(dates)

        # Returns first matching, which is 07-20 (first valid in list)
        self.assertEqual(result, "2026-07-20")

    def test_all_dates_outside_range(self):
        """All dates outside range should return None."""
        from visa import get_available_date

        dates = [
            {"date": "2026-01-15"},
            {"date": "2026-02-15"},
            {"date": "2027-03-15"},
        ]

        result = get_available_date(dates)

        self.assertIsNone(result)

    def test_mixed_format_dates(self):
        """Handle mixed dict and string formats (edge case)."""
        from visa import get_available_date

        # In practice, API returns consistent format, but test robustness
        dates = [
            {"date": "2026-05-15"},  # Dict, before range
            "2026-07-15",            # String, in range
        ]

        result = get_available_date(dates)

        self.assertEqual(result, "2026-07-15")

    def test_none_date_in_list(self):
        """Handle None values in date list gracefully."""
        from visa import get_available_date

        dates = [
            {"date": None},
            {"date": "2026-07-15"},
        ]

        result = get_available_date(dates)

        self.assertEqual(result, "2026-07-15")

    def test_dict_without_date_key(self):
        """Handle dict without 'date' key."""
        from visa import get_available_date

        dates = [
            {"business_day": True},  # Missing 'date' key
            {"date": "2026-07-15"},
        ]

        result = get_available_date(dates)

        self.assertEqual(result, "2026-07-15")


class TestDateBoundaryEdgeCases(unittest.TestCase):
    """Test edge cases for date boundary handling."""

    def setUp(self):
        """Set up with narrow date range for precise boundary testing."""
        self.priod_start_patcher = patch('visa.PRIOD_START', '2026-07-10')
        self.priod_end_patcher = patch('visa.PRIOD_END', '2026-07-20')
        self.logger_patcher = patch('visa.get_logger')

        self.mock_priod_start = self.priod_start_patcher.start()
        self.mock_priod_end = self.priod_end_patcher.start()
        self.mock_logger = self.logger_patcher.start()
        self.mock_logger.return_value = MagicMock()

    def tearDown(self):
        self.priod_start_patcher.stop()
        self.priod_end_patcher.stop()
        self.logger_patcher.stop()

    def test_day_before_start(self):
        """Day before PRIOD_START should be excluded."""
        from visa import get_available_date

        dates = [{"date": "2026-07-09"}]

        result = get_available_date(dates)

        self.assertIsNone(result)

    def test_day_after_end(self):
        """Day after PRIOD_END should be excluded."""
        from visa import get_available_date

        dates = [{"date": "2026-07-21"}]

        result = get_available_date(dates)

        self.assertIsNone(result)

    def test_single_day_range(self):
        """Test when PRIOD_START equals PRIOD_END (single day)."""
        with patch('visa.PRIOD_START', '2026-07-15'), \
             patch('visa.PRIOD_END', '2026-07-15'):
            from visa import get_available_date

            # Reload to pick up new patch values
            dates = [{"date": "2026-07-15"}]
            result = get_available_date(dates)

            self.assertEqual(result, "2026-07-15")


class TestDateFilteringWithRealAPIFormats(unittest.TestCase):
    """Test with realistic API response formats."""

    def setUp(self):
        self.priod_start_patcher = patch('visa.PRIOD_START', '2026-06-01')
        self.priod_end_patcher = patch('visa.PRIOD_END', '2026-12-31')
        self.logger_patcher = patch('visa.get_logger')

        self.mock_priod_start = self.priod_start_patcher.start()
        self.mock_priod_end = self.priod_end_patcher.start()
        self.mock_logger = self.logger_patcher.start()
        self.mock_logger.return_value = MagicMock()

    def tearDown(self):
        self.priod_start_patcher.stop()
        self.priod_end_patcher.stop()
        self.logger_patcher.stop()

    def test_real_api_response_format(self):
        """Test with actual API response format."""
        from visa import get_available_date

        # Actual format from usvisa-info.com API
        dates = [
            {"date": "2026-07-15"},
            {"date": "2026-07-16"},
            {"date": "2026-07-19"},
            {"date": "2026-07-20"},
        ]

        result = get_available_date(dates)

        self.assertEqual(result, "2026-07-15")

    def test_sorted_dates_earliest_first(self):
        """API typically returns dates sorted earliest first."""
        from visa import get_available_date

        dates = [
            {"date": "2026-07-15"},  # Earliest
            {"date": "2026-07-16"},
            {"date": "2026-08-01"},
            {"date": "2026-09-15"},  # Latest
        ]

        result = get_available_date(dates)

        # Should get first (earliest) matching date
        self.assertEqual(result, "2026-07-15")

    def test_large_date_list(self):
        """Handle large list of dates efficiently."""
        from visa import get_available_date

        # Simulate many dates (API could return 30+ days)
        dates = [{"date": f"2026-07-{day:02d}"} for day in range(1, 31)]

        result = get_available_date(dates)

        # First date in range
        self.assertEqual(result, "2026-07-01")


class TestDateFilteringLogging(unittest.TestCase):
    """Test logging behavior of date filtering."""

    def setUp(self):
        self.priod_start_patcher = patch('visa.PRIOD_START', '2026-06-01')
        self.priod_end_patcher = patch('visa.PRIOD_END', '2026-06-30')
        self.logger_patcher = patch('visa.get_logger')

        self.mock_priod_start = self.priod_start_patcher.start()
        self.mock_priod_end = self.priod_end_patcher.start()
        self.mock_get_logger = self.logger_patcher.start()
        self.mock_logger = MagicMock()
        self.mock_get_logger.return_value = self.mock_logger

    def tearDown(self):
        self.priod_start_patcher.stop()
        self.priod_end_patcher.stop()
        self.logger_patcher.stop()

    def test_logs_when_no_dates_in_range(self):
        """Should log info when no dates match target range."""
        from visa import get_available_date

        dates = [{"date": "2026-07-15"}]  # Outside range

        result = get_available_date(dates)

        self.assertIsNone(result)
        # Verify logging was called
        self.mock_logger.info.assert_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
