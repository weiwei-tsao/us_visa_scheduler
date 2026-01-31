"""
Integration tests for the full visa scheduler system.

End-to-end tests verifying all components work together correctly.
"""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import configparser
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFullFlowNoProxy(unittest.TestCase):
    """Test complete flow without proxy."""

    def test_config_loads_without_proxy(self):
        """Should load config and initialize without proxy."""
        from proxy_manager import load_proxy_config
        from visa import (
            load_ban_detection_config,
            get_retry_time_bounds,
            validate_config
        )

        config = configparser.ConfigParser()
        config['PERSONAL_INFO'] = {
            'USERNAME': 'test@example.com',
            'PASSWORD': 'testpass',
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
        config['NOTIFICATION'] = {
            'SENDGRID_API_KEY': 'test_key',
            'TELEGRAM_BOT_TOKEN': ''
        }

        # Validate config
        errors, warnings = validate_config(config)
        self.assertEqual(len(errors), 0)

        # Load ban detection config
        ban_config = load_ban_detection_config(config)
        self.assertEqual(ban_config['first'], 5)  # Default

        # Load proxy config
        proxy_enabled, proxy_manager = load_proxy_config(config)
        self.assertFalse(proxy_enabled)
        self.assertIsNone(proxy_manager)

        # Get retry bounds
        lower, upper = get_retry_time_bounds(config)
        self.assertEqual(lower, 60)
        self.assertEqual(upper, 120)

    def test_graduated_ban_detection_flow(self):
        """Test graduated ban detection through multiple empty responses."""
        from visa import handle_empty_response, DEFAULT_BAN_COOLDOWNS

        cooldown_config = DEFAULT_BAN_COOLDOWNS.copy()

        # First empty - short cooldown
        with patch('visa.send_notification'):
            result1 = handle_empty_response(1, cooldown_config)
            self.assertEqual(result1['action'], 'sleep')
            self.assertEqual(result1['duration'], 5 * 60)  # 5 minutes

        # Second empty - medium cooldown
        with patch('visa.send_notification'):
            result2 = handle_empty_response(2, cooldown_config)
            self.assertEqual(result2['action'], 'sleep')
            self.assertEqual(result2['duration'], 30 * 60)  # 30 minutes

        # Third empty - long cooldown
        with patch('visa.send_notification'):
            result3 = handle_empty_response(3, cooldown_config)
            self.assertEqual(result3['action'], 'sleep')
            self.assertEqual(result3['duration'], 120 * 60)  # 2 hours

        # Fourth empty - exit
        with patch('visa.send_notification'):
            result4 = handle_empty_response(4, cooldown_config)
            self.assertEqual(result4['action'], 'exit')


class TestFullFlowWithProxy(unittest.TestCase):
    """Test complete flow with proxy enabled."""

    def test_config_loads_with_proxy(self):
        """Should load config and initialize with proxy."""
        from proxy_manager import load_proxy_config
        from visa import validate_config

        config = configparser.ConfigParser()
        config['PERSONAL_INFO'] = {
            'USERNAME': 'test@example.com',
            'PASSWORD': 'testpass',
            'SCHEDULE_ID': '12345678',
            'PRIOD_START': '2026-01-01',
            'PRIOD_END': '2026-12-31',
            'YOUR_EMBASSY': 'en-ca-tor'
        }
        config['TIME'] = {
            'RETRY_TIME_L_BOUND': '30',  # Aggressive
            'RETRY_TIME_U_BOUND': '45',
        }
        config['PROXY'] = {
            'ENABLED': 'True',
            'PROXY_LIST': 'http://proxy1.example.com:8080\nhttp://proxy2.example.com:8080',
            'ROTATION_STRATEGY': 'on_ban',
            'HEALTH_CHECK': 'False'
        }
        config['NOTIFICATION'] = {
            'SENDGRID_API_KEY': 'test_key',
            'TELEGRAM_BOT_TOKEN': ''
        }

        # Validate config - no warning for aggressive polling with proxy
        errors, warnings = validate_config(config)
        self.assertEqual(len(errors), 0)
        aggressive_warnings = [w for w in warnings if 'aggressive' in w.lower()]
        self.assertEqual(len(aggressive_warnings), 0)

        # Load proxy config
        proxy_enabled, proxy_manager = load_proxy_config(config)
        self.assertTrue(proxy_enabled)
        self.assertIsNotNone(proxy_manager)
        self.assertEqual(proxy_manager.total_count, 2)
        self.assertEqual(proxy_manager.rotation_strategy, 'on_ban')

    def test_proxy_rotation_on_ban_flow(self):
        """Test proxy rotation when ban is detected."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080',
            'http://proxy3.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies, rotation_strategy='on_ban')

        # Initial proxy
        initial = manager.get_proxy()
        self.assertEqual(initial['host'], 'proxy1.example.com')

        # Simulate ban - rotate
        manager.rotate()
        second = manager.get_proxy()
        self.assertEqual(second['host'], 'proxy2.example.com')

        # Another ban - rotate again
        manager.rotate()
        third = manager.get_proxy()
        self.assertEqual(third['host'], 'proxy3.example.com')

        # Another ban - wraps around
        manager.rotate()
        fourth = manager.get_proxy()
        self.assertEqual(fourth['host'], 'proxy1.example.com')


class TestConfigMigration(unittest.TestCase):
    """Test backward compatibility with old config files."""

    def test_old_config_without_ban_detection(self):
        """Should work with config missing BAN_DETECTION section."""
        from visa import load_ban_detection_config, DEFAULT_BAN_COOLDOWNS

        config = configparser.ConfigParser()
        config['PERSONAL_INFO'] = {
            'USERNAME': 'test@example.com',
            'PASSWORD': 'testpass',
            'SCHEDULE_ID': '12345678',
            'PRIOD_START': '2026-01-01',
            'PRIOD_END': '2026-12-31',
            'YOUR_EMBASSY': 'en-ca-tor'
        }
        # No BAN_DETECTION section

        ban_config = load_ban_detection_config(config)

        # Should use defaults
        self.assertEqual(ban_config['first'], DEFAULT_BAN_COOLDOWNS['first'])
        self.assertEqual(ban_config['second'], DEFAULT_BAN_COOLDOWNS['second'])
        self.assertEqual(ban_config['third'], DEFAULT_BAN_COOLDOWNS['third'])
        self.assertEqual(ban_config['hard_ban'], DEFAULT_BAN_COOLDOWNS['hard_ban'])

    def test_old_config_without_proxy(self):
        """Should work with config missing PROXY section."""
        from proxy_manager import load_proxy_config

        config = configparser.ConfigParser()
        # No PROXY section

        enabled, manager = load_proxy_config(config)

        self.assertFalse(enabled)
        self.assertIsNone(manager)

    def test_old_config_without_time_section(self):
        """Should use defaults when TIME section is missing."""
        from visa import get_retry_time_bounds, DEFAULT_RETRY_TIME_L_BOUND, DEFAULT_RETRY_TIME_U_BOUND

        config = configparser.ConfigParser()
        # No TIME section

        lower, upper = get_retry_time_bounds(config)

        self.assertEqual(lower, DEFAULT_RETRY_TIME_L_BOUND)
        self.assertEqual(upper, DEFAULT_RETRY_TIME_U_BOUND)


class TestLoggingFormat(unittest.TestCase):
    """Test logging format for analysis scripts."""

    def test_ban_response_logging(self):
        """Ban responses should log in parseable format."""
        from visa import handle_empty_response, DEFAULT_BAN_COOLDOWNS
        import tempfile
        import os

        cooldown_config = DEFAULT_BAN_COOLDOWNS.copy()

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            log_file = f.name

        try:
            with patch('visa.send_notification'):
                handle_empty_response(1, cooldown_config, log_file=log_file)

            with open(log_file, 'r') as f:
                content = f.read()

            # Should contain BAN marker for parsing
            self.assertIn('[BAN]', content)
            self.assertIn('Empty response', content)
        finally:
            os.unlink(log_file)


class TestHardBanDetection(unittest.TestCase):
    """Test hard ban detection from HTTP responses."""

    def test_http_403_detected_as_ban(self):
        """HTTP 403 should be detected as hard ban."""
        from visa import is_hard_ban_response

        result = is_hard_ban_response(403, '')
        self.assertTrue(result)

    def test_http_429_detected_as_ban(self):
        """HTTP 429 should be detected as hard ban."""
        from visa import is_hard_ban_response

        result = is_hard_ban_response(429, '')
        self.assertTrue(result)

    def test_cloudflare_signatures_detected(self):
        """Cloudflare ban signatures should be detected."""
        from visa import is_hard_ban_response

        # Error 1015
        result1 = is_hard_ban_response(200, 'Error 1015: You are being rate limited')
        self.assertTrue(result1)

        # Access denied
        result2 = is_hard_ban_response(200, 'Access denied by security policy')
        self.assertTrue(result2)

        # CF-Ray header in response
        result3 = is_hard_ban_response(200, 'blocked cf-ray: abc123')
        self.assertTrue(result3)

    def test_normal_response_not_ban(self):
        """Normal 200 response should not be detected as ban."""
        from visa import is_hard_ban_response

        result = is_hard_ban_response(200, '[{"date": "2026-03-15"}]')
        self.assertFalse(result)


class TestBanCooldownCalculation(unittest.TestCase):
    """Test cooldown calculation for various scenarios."""

    def test_retry_after_header_respected(self):
        """Should respect Retry-After header value."""
        from visa import get_ban_cooldown, DEFAULT_BAN_COOLDOWNS

        cooldown = get_ban_cooldown(
            consecutive_empty_count=1,
            http_status=429,
            cooldown_config=DEFAULT_BAN_COOLDOWNS,
            retry_after=300  # 5 minutes
        )

        self.assertEqual(cooldown, 300)

    def test_hard_ban_without_retry_after(self):
        """Should use config value when no Retry-After header."""
        from visa import get_ban_cooldown, DEFAULT_BAN_COOLDOWNS

        cooldown = get_ban_cooldown(
            consecutive_empty_count=1,
            http_status=403,
            cooldown_config=DEFAULT_BAN_COOLDOWNS,
            retry_after=None
        )

        self.assertEqual(cooldown, DEFAULT_BAN_COOLDOWNS['hard_ban'] * 60)


class TestProxyFailover(unittest.TestCase):
    """Test proxy failover behavior."""

    def test_all_proxies_failed_returns_none(self):
        """Should return None when all proxies fail."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=[
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080'
        ])

        manager.mark_failed('http://proxy1.example.com:8080')
        manager.mark_failed('http://proxy2.example.com:8080')

        self.assertIsNone(manager.get_proxy())
        self.assertIsNone(manager.rotate())

    def test_reset_failed_restores_proxies(self):
        """Should restore all proxies after reset."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=[
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080'
        ])

        manager.mark_failed('http://proxy1.example.com:8080')
        manager.mark_failed('http://proxy2.example.com:8080')
        self.assertEqual(manager.available_count, 0)

        manager.reset_failed()
        self.assertEqual(manager.available_count, 2)


class TestEndToEndScenarios(unittest.TestCase):
    """End-to-end scenario tests."""

    def test_scenario_normal_operation(self):
        """Scenario: Normal operation with dates returned."""
        from visa import (
            validate_config,
            get_retry_time_bounds,
            load_ban_detection_config
        )

        # Setup config
        config = configparser.ConfigParser()
        config['PERSONAL_INFO'] = {
            'USERNAME': 'test@example.com',
            'PASSWORD': 'testpass',
            'SCHEDULE_ID': '12345678',
            'PRIOD_START': '2026-01-01',
            'PRIOD_END': '2026-12-31',
            'YOUR_EMBASSY': 'en-ca-tor'
        }
        config['TIME'] = {
            'RETRY_TIME_L_BOUND': '60',
            'RETRY_TIME_U_BOUND': '120',
        }
        config['NOTIFICATION'] = {
            'SENDGRID_API_KEY': 'key',
            'TELEGRAM_BOT_TOKEN': 'token'
        }

        # Validate
        errors, warnings = validate_config(config)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 0)  # Has notifications configured

    def test_scenario_progressive_ban_recovery(self):
        """Scenario: Progressive recovery from potential ban."""
        from visa import handle_empty_response, DEFAULT_BAN_COOLDOWNS
        from proxy_manager import ProxyManager

        cooldown_config = DEFAULT_BAN_COOLDOWNS.copy()
        consecutive_empty = 0

        # Simulate series of empty responses
        with patch('visa.send_notification'):
            # First empty - short wait
            consecutive_empty += 1
            result = handle_empty_response(consecutive_empty, cooldown_config)
            self.assertEqual(result['action'], 'sleep')
            self.assertEqual(result['duration'], 5 * 60)

            # Simulate getting dates - reset counter
            # (In real code, this happens when dates are returned)
            consecutive_empty = 0

            # New first empty after recovery
            consecutive_empty += 1
            result = handle_empty_response(consecutive_empty, cooldown_config)
            self.assertEqual(result['duration'], 5 * 60)  # Back to first level

    def test_scenario_proxy_rotation_sequence(self):
        """Scenario: Full proxy rotation cycle."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080',
            'http://proxy3.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies, rotation_strategy='on_ban')

        rotation_sequence = []
        for _ in range(6):  # 2 full cycles
            proxy = manager.get_proxy()
            rotation_sequence.append(proxy['host'])
            manager.rotate()

        # Should cycle through all proxies twice
        expected = [
            'proxy1.example.com',
            'proxy2.example.com',
            'proxy3.example.com',
            'proxy1.example.com',
            'proxy2.example.com',
            'proxy3.example.com'
        ]
        self.assertEqual(rotation_sequence, expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
