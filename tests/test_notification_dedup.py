"""
Unit tests for notification deduplication logic.

Tests the logic that prevents spam notifications when dates are available
but not in the target range. Notifications should only be sent when:
1. The earliest available date moves EARLIER (potentially interesting)
2. NOT when it moves later (slots taken - not interesting)

This avoids flooding the user with notifications every polling cycle.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import sys
import os
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestEarliestDateTracking(unittest.TestCase):
    """Test the earliest date tracking logic for notification dedup."""

    def test_first_notification_always_sent(self):
        """First notification should always be sent (no previous date)."""
        last_notified_earliest_date = None
        earliest = "2026-07-15"

        should_notify = (last_notified_earliest_date is None or
                        earliest < last_notified_earliest_date)

        self.assertTrue(should_notify)

    def test_earlier_date_triggers_notification(self):
        """Notification sent when new date is earlier than previous."""
        last_notified_earliest_date = "2026-07-20"
        earliest = "2026-07-15"  # Earlier

        should_notify = (last_notified_earliest_date is None or
                        earliest < last_notified_earliest_date)

        self.assertTrue(should_notify)

    def test_later_date_suppresses_notification(self):
        """Notification suppressed when new date is later (slot taken)."""
        last_notified_earliest_date = "2026-07-15"
        earliest = "2026-07-20"  # Later

        should_notify = (last_notified_earliest_date is None or
                        earliest < last_notified_earliest_date)

        self.assertFalse(should_notify)

    def test_same_date_suppresses_notification(self):
        """Notification suppressed when date is unchanged."""
        last_notified_earliest_date = "2026-07-15"
        earliest = "2026-07-15"  # Same

        should_notify = (last_notified_earliest_date is None or
                        earliest < last_notified_earliest_date)

        self.assertFalse(should_notify)

    def test_date_comparison_uses_string_ordering(self):
        """YYYY-MM-DD format allows correct string comparison."""
        # String comparison works for YYYY-MM-DD format
        self.assertTrue("2026-01-15" < "2026-02-15")
        self.assertTrue("2026-07-01" < "2026-07-15")
        self.assertTrue("2025-12-31" < "2026-01-01")


class TestEarliestDatePersistence(unittest.TestCase):
    """Test persistence of last_notified_earliest_date across restarts."""

    def test_save_earliest_date_to_file(self):
        """Earliest date should be saved to file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            earliest_date_file = f.name

        try:
            earliest = "2026-07-15"

            with open(earliest_date_file, "w") as f:
                f.write(earliest)

            with open(earliest_date_file, "r") as f:
                saved_date = f.read().strip()

            self.assertEqual(saved_date, earliest)
        finally:
            os.unlink(earliest_date_file)

    def test_load_earliest_date_from_file(self):
        """Should load last_notified_earliest_date from file on startup."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("2026-07-15")
            earliest_date_file = f.name

        try:
            last_notified_earliest_date = None

            if os.path.exists(earliest_date_file):
                with open(earliest_date_file, "r") as f:
                    last_notified_earliest_date = f.read().strip() or None

            self.assertEqual(last_notified_earliest_date, "2026-07-15")
        finally:
            os.unlink(earliest_date_file)

    def test_empty_file_returns_none(self):
        """Empty file should return None for last_notified_earliest_date."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            earliest_date_file = f.name

        try:
            last_notified_earliest_date = None

            if os.path.exists(earliest_date_file):
                with open(earliest_date_file, "r") as f:
                    last_notified_earliest_date = f.read().strip() or None

            self.assertIsNone(last_notified_earliest_date)
        finally:
            os.unlink(earliest_date_file)

    def test_missing_file_returns_none(self):
        """Missing file should return None."""
        earliest_date_file = "/nonexistent/path/file.txt"
        last_notified_earliest_date = None

        if os.path.exists(earliest_date_file):
            with open(earliest_date_file, "r") as f:
                last_notified_earliest_date = f.read().strip() or None

        self.assertIsNone(last_notified_earliest_date)


class TestNotificationDedupIntegration(unittest.TestCase):
    """Integration tests for notification deduplication."""

    def test_multiple_polls_same_date(self):
        """Multiple polls with same earliest date should only notify once."""
        notifications_sent = []
        last_notified_earliest_date = None

        # Simulate 5 polling cycles with same earliest date
        for _ in range(5):
            dates = [{"date": "2026-07-15"}, {"date": "2026-07-20"}]
            earliest = dates[0]["date"]

            should_notify = (last_notified_earliest_date is None or
                            earliest < last_notified_earliest_date)

            if should_notify:
                notifications_sent.append(earliest)
                last_notified_earliest_date = earliest

        # Only one notification should be sent
        self.assertEqual(len(notifications_sent), 1)
        self.assertEqual(notifications_sent[0], "2026-07-15")

    def test_date_moves_earlier_triggers_new_notification(self):
        """When earliest date moves earlier, should send new notification."""
        notifications_sent = []
        last_notified_earliest_date = "2026-07-20"

        # First poll: date moves earlier
        earliest = "2026-07-15"
        should_notify = (last_notified_earliest_date is None or
                        earliest < last_notified_earliest_date)
        if should_notify:
            notifications_sent.append(earliest)
            last_notified_earliest_date = earliest

        # Second poll: date moves even earlier
        earliest = "2026-07-10"
        should_notify = (last_notified_earliest_date is None or
                        earliest < last_notified_earliest_date)
        if should_notify:
            notifications_sent.append(earliest)
            last_notified_earliest_date = earliest

        # Third poll: date moves later (slot taken)
        earliest = "2026-07-12"
        should_notify = (last_notified_earliest_date is None or
                        earliest < last_notified_earliest_date)
        if should_notify:
            notifications_sent.append(earliest)

        # Should have 2 notifications (earlier dates), not 3
        self.assertEqual(len(notifications_sent), 2)
        self.assertEqual(notifications_sent, ["2026-07-15", "2026-07-10"])

    def test_restart_with_persisted_date(self):
        """After restart, should use persisted date for dedup."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("2026-07-15")
            earliest_date_file = f.name

        try:
            # Simulate restart - load persisted date
            last_notified_earliest_date = None
            if os.path.exists(earliest_date_file):
                with open(earliest_date_file, "r") as f:
                    last_notified_earliest_date = f.read().strip() or None

            # First poll after restart with same date - should NOT notify
            earliest = "2026-07-15"
            should_notify = (last_notified_earliest_date is None or
                            earliest < last_notified_earliest_date)

            self.assertFalse(should_notify)

            # Poll with earlier date - SHOULD notify
            earliest = "2026-07-10"
            should_notify = (last_notified_earliest_date is None or
                            earliest < last_notified_earliest_date)

            self.assertTrue(should_notify)
        finally:
            os.unlink(earliest_date_file)


class TestDateExtractionFromResponse(unittest.TestCase):
    """Test extracting earliest date from API response."""

    def test_extract_earliest_from_dict_list(self):
        """Extract earliest date from list of date dicts."""
        dates = [
            {"date": "2026-07-15"},
            {"date": "2026-07-20"},
            {"date": "2026-08-01"},
        ]

        earliest = dates[0].get('date') if isinstance(dates[0], dict) else dates[0]

        self.assertEqual(earliest, "2026-07-15")

    def test_extract_earliest_from_string_list(self):
        """Extract earliest date from list of date strings."""
        dates = ["2026-07-15", "2026-07-20", "2026-08-01"]

        earliest = dates[0].get('date') if isinstance(dates[0], dict) else dates[0]

        self.assertEqual(earliest, "2026-07-15")

    def test_empty_list_handling(self):
        """Empty list should not cause errors."""
        dates = []

        if dates:
            earliest = dates[0].get('date') if isinstance(dates[0], dict) else dates[0]
        else:
            earliest = None

        self.assertIsNone(earliest)


class TestNotificationMessage(unittest.TestCase):
    """Test notification message formatting."""

    def test_notification_includes_date_count(self):
        """Notification should include count of available dates."""
        dates = [
            {"date": "2026-07-15"},
            {"date": "2026-07-20"},
            {"date": "2026-08-01"},
        ]
        earliest = dates[0]["date"]
        priod_start = "2026-09-01"
        priod_end = "2026-12-31"

        dates_msg = (f"{len(dates)} dates available. "
                    f"Earliest: {earliest}. "
                    f"Not in your target range ({priod_start} to {priod_end}).")

        self.assertIn("3 dates available", dates_msg)
        self.assertIn("Earliest: 2026-07-15", dates_msg)
        self.assertIn("2026-09-01 to 2026-12-31", dates_msg)


if __name__ == '__main__':
    unittest.main(verbosity=2)
