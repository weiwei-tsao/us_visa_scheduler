"""
Unit tests for configuration validation.

Tests validation of polling intervals, date ranges, and other config parameters.
"""

import unittest
from unittest.mock import patch, MagicMock
import configparser
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRetryTimeValidation(unittest.TestCase):
    """Test validation of RETRY_TIME bounds."""

    def test_valid_retry_time_bounds(self):
        """Valid bounds should pass validation."""
        from visa import validate_retry_time_config

        errors = validate_retry_time_config(
            lower_bound=60,
            upper_bound=120
        )

        self.assertEqual(len(errors), 0)

    def test_invalid_bounds_lower_greater_than_upper(self):
        """Should error when lower bound > upper bound."""
        from visa import validate_retry_time_config

        errors = validate_retry_time_config(
            lower_bound=300,
            upper_bound=100
        )

        self.assertEqual(len(errors), 1)
        self.assertIn('lower', errors[0].lower())
        self.assertIn('upper', errors[0].lower())

    def test_zero_interval_rejected(self):
        """Zero interval should be rejected."""
        from visa import validate_retry_time_config

        errors = validate_retry_time_config(
            lower_bound=0,
            upper_bound=60
        )

        self.assertEqual(len(errors), 1)
        self.assertIn('greater than 0', errors[0].lower())

    def test_negative_interval_rejected(self):
        """Negative interval should be rejected."""
        from visa import validate_retry_time_config

        errors = validate_retry_time_config(
            lower_bound=-10,
            upper_bound=60
        )

        self.assertEqual(len(errors), 1)

    def test_negative_upper_bound_rejected(self):
        """Negative upper bound should be rejected."""
        from visa import validate_retry_time_config

        errors = validate_retry_time_config(
            lower_bound=10,
            upper_bound=-5
        )

        self.assertGreater(len(errors), 0)


class TestAggressiveIntervalWarning(unittest.TestCase):
    """Test warnings for aggressive polling intervals."""

    def test_aggressive_interval_warning_no_proxy(self):
        """Intervals < 60s without proxy should generate warning."""
        from visa import get_config_warnings

        warnings = get_config_warnings(
            lower_bound=10,
            upper_bound=30,
            proxy_enabled=False
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn('aggressive', warnings[0].lower())

    def test_aggressive_interval_no_warning_with_proxy(self):
        """Aggressive intervals WITH proxy should not warn."""
        from visa import get_config_warnings

        warnings = get_config_warnings(
            lower_bound=10,
            upper_bound=30,
            proxy_enabled=True
        )

        self.assertEqual(len(warnings), 0)

    def test_moderate_interval_no_warning(self):
        """Moderate intervals (60-120s) should not warn."""
        from visa import get_config_warnings

        warnings = get_config_warnings(
            lower_bound=60,
            upper_bound=120,
            proxy_enabled=False
        )

        self.assertEqual(len(warnings), 0)

    def test_conservative_interval_no_warning(self):
        """Conservative intervals (111-300s) should not warn."""
        from visa import get_config_warnings

        warnings = get_config_warnings(
            lower_bound=111,
            upper_bound=300,
            proxy_enabled=False
        )

        self.assertEqual(len(warnings), 0)


class TestDateValidation(unittest.TestCase):
    """Test validation of date configuration."""

    def test_valid_date_range(self):
        """Valid date range should pass."""
        from visa import validate_date_config

        errors = validate_date_config(
            start_date="2026-01-01",
            end_date="2026-12-31"
        )

        self.assertEqual(len(errors), 0)

    def test_invalid_date_format_start(self):
        """Invalid start date format should error."""
        from visa import validate_date_config

        errors = validate_date_config(
            start_date="01-01-2026",  # Wrong format
            end_date="2026-12-31"
        )

        self.assertEqual(len(errors), 1)
        self.assertIn('start', errors[0].lower())

    def test_invalid_date_format_end(self):
        """Invalid end date format should error."""
        from visa import validate_date_config

        errors = validate_date_config(
            start_date="2026-01-01",
            end_date="12/31/2026"  # Wrong format
        )

        self.assertEqual(len(errors), 1)
        self.assertIn('end', errors[0].lower())

    def test_start_after_end(self):
        """Start date after end date should error."""
        from visa import validate_date_config

        errors = validate_date_config(
            start_date="2026-12-31",
            end_date="2026-01-01"
        )

        self.assertEqual(len(errors), 1)
        self.assertIn('before', errors[0].lower())


class TestEmbassyValidation(unittest.TestCase):
    """Test validation of embassy configuration."""

    def test_valid_embassy_code(self):
        """Valid embassy code should pass."""
        from visa import validate_embassy_config

        errors = validate_embassy_config("en-ca-tor")

        self.assertEqual(len(errors), 0)

    def test_invalid_embassy_code(self):
        """Invalid embassy code should error."""
        from visa import validate_embassy_config

        errors = validate_embassy_config("invalid-embassy-xyz")

        self.assertEqual(len(errors), 1)
        self.assertIn('embassy', errors[0].lower())


class TestFullConfigValidation(unittest.TestCase):
    """Test full configuration validation."""

    def test_valid_full_config(self):
        """Complete valid config should pass all validations."""
        from visa import validate_config

        config = configparser.ConfigParser()
        config['PERSONAL_INFO'] = {
            'USERNAME': 'test@example.com',
            'PASSWORD': 'test',
            'SCHEDULE_ID': '12345678',
            'PRIOD_START': '2026-01-01',
            'PRIOD_END': '2026-12-31',
            'YOUR_EMBASSY': 'en-ca-tor'
        }
        config['TIME'] = {
            'RETRY_TIME_L_BOUND': '60',
            'RETRY_TIME_U_BOUND': '120',
            'WORK_LIMIT_TIME': '0.75'
        }
        config['CHROMEDRIVER'] = {
            'LOCAL_USE': 'True',
            'HUB_ADDRESS': 'http://localhost:4444'
        }
        config['NOTIFICATION'] = {
            'SENDGRID_API_KEY': '',
            'SENDGRID_EMAIL_SENDER': ''
        }

        errors, warnings = validate_config(config)

        self.assertEqual(len(errors), 0)

    def test_missing_required_section(self):
        """Missing required section should error."""
        from visa import validate_config

        config = configparser.ConfigParser()
        # Missing PERSONAL_INFO section

        errors, warnings = validate_config(config)

        self.assertGreater(len(errors), 0)


class TestDefaultsOnMissingConfig(unittest.TestCase):
    """Test that missing config values use sensible defaults."""

    def test_missing_time_section_uses_defaults(self):
        """Missing TIME section should use default values."""
        config = configparser.ConfigParser()
        config['PERSONAL_INFO'] = {
            'USERNAME': 'test@example.com',
            'PASSWORD': 'test',
            'SCHEDULE_ID': '12345',
            'PRIOD_START': '2026-01-01',
            'PRIOD_END': '2026-12-31',
            'YOUR_EMBASSY': 'en-ca-tor'
        }
        # No TIME section

        from visa import get_retry_time_bounds

        lower, upper = get_retry_time_bounds(config)

        # Should return defaults (111, 300)
        self.assertEqual(lower, 111)
        self.assertEqual(upper, 300)

    def test_partial_time_section_uses_defaults(self):
        """Partial TIME section should use defaults for missing values."""
        config = configparser.ConfigParser()
        config['TIME'] = {
            'RETRY_TIME_L_BOUND': '60'
            # Missing RETRY_TIME_U_BOUND
        }

        from visa import get_retry_time_bounds

        lower, upper = get_retry_time_bounds(config)

        self.assertEqual(lower, 60)
        self.assertEqual(upper, 300)  # Default


class TestNotificationWarnings(unittest.TestCase):
    """Test warnings for notification configuration."""

    def test_no_notifications_configured_warning(self):
        """Should warn when no notifications are configured."""
        from visa import get_config_warnings

        warnings = get_config_warnings(
            lower_bound=60,
            upper_bound=120,
            proxy_enabled=False,
            sendgrid_configured=False,
            telegram_configured=False
        )

        # Should have warning about no notifications
        notification_warnings = [w for w in warnings if 'notification' in w.lower()]
        self.assertEqual(len(notification_warnings), 1)

    def test_notifications_configured_no_warning(self):
        """Should not warn when notifications are configured."""
        from visa import get_config_warnings

        warnings = get_config_warnings(
            lower_bound=60,
            upper_bound=120,
            proxy_enabled=False,
            sendgrid_configured=True,
            telegram_configured=False
        )

        notification_warnings = [w for w in warnings if 'notification' in w.lower()]
        self.assertEqual(len(notification_warnings), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
