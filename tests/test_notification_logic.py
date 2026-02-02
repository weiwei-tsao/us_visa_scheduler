"""
Tests for earliest date notification logic.

The notification logic should:
- Notify when earliest date is EARLIER than previously recorded (good news)
- NOT notify when earliest date is LATER or same (not interesting)
"""

import pytest


def should_notify_earliest_date(earliest: str, last_notified: str | None) -> bool:
    """
    Determines if we should notify about a new earliest date.

    Args:
        earliest: The new earliest available date (YYYY-MM-DD format)
        last_notified: The previously notified earliest date, or None if first run

    Returns:
        True if we should notify (date moved earlier), False otherwise
    """
    return last_notified is None or earliest < last_notified


class TestEarliestDateNotification:
    """Test cases for earliest date notification logic."""

    def test_first_run_should_notify(self):
        """When last_notified is None (first run), should always notify."""
        assert should_notify_earliest_date("2027-07-16", None) is True
        assert should_notify_earliest_date("2027-12-31", None) is True

    def test_date_moved_earlier_should_notify(self):
        """When new date is earlier than recorded, should notify (good news)."""
        # 07-15 < 07-16 = date moved earlier
        assert should_notify_earliest_date("2027-07-15", "2027-07-16") is True
        # 06-01 < 07-16 = date moved much earlier
        assert should_notify_earliest_date("2027-06-01", "2027-07-16") is True
        # Previous year is earlier
        assert should_notify_earliest_date("2026-12-31", "2027-01-01") is True

    def test_date_moved_later_should_not_notify(self):
        """When new date is later than recorded, should NOT notify (slots taken)."""
        # 07-20 > 07-16 = date moved later
        assert should_notify_earliest_date("2027-07-20", "2027-07-16") is False
        # 08-01 > 07-16 = date moved much later
        assert should_notify_earliest_date("2027-08-01", "2027-07-16") is False
        # Next year is later
        assert should_notify_earliest_date("2028-01-01", "2027-12-31") is False

    def test_same_date_should_not_notify(self):
        """When new date is same as recorded, should NOT notify (no change)."""
        assert should_notify_earliest_date("2027-07-16", "2027-07-16") is False

    def test_string_comparison_works_for_dates(self):
        """Verify YYYY-MM-DD format allows correct string comparison."""
        # String comparison should work correctly for ISO date format
        assert "2027-01-01" < "2027-01-02"  # Day comparison
        assert "2027-01-31" < "2027-02-01"  # Month boundary
        assert "2027-12-31" < "2028-01-01"  # Year boundary
        assert "2027-07-15" < "2027-07-16"  # The actual use case


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
