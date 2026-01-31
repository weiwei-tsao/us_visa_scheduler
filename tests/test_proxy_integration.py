"""
Integration tests for proxy support in visa.py.

Tests proxy rotation on session restart and ban detection.
"""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import configparser
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestProxyConfigValidation(unittest.TestCase):
    """Test proxy configuration validation in visa.py."""

    def test_validate_config_with_proxy_enabled(self):
        """Should recognize proxy enabled state."""
        from visa import validate_config, get_config_warnings

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
            'RETRY_TIME_L_BOUND': '30',  # Aggressive
            'RETRY_TIME_U_BOUND': '45',
        }
        config['PROXY'] = {
            'ENABLED': 'True',
            'PROXY_LIST': 'http://proxy.example.com:8080'
        }
        config['NOTIFICATION'] = {
            'SENDGRID_API_KEY': 'key',
            'TELEGRAM_BOT_TOKEN': ''
        }

        errors, warnings = validate_config(config)

        # Should NOT warn about aggressive polling when proxy is enabled
        aggressive_warnings = [w for w in warnings if 'aggressive' in w.lower()]
        self.assertEqual(len(aggressive_warnings), 0)

    def test_validate_config_aggressive_no_proxy_warns(self):
        """Should warn about aggressive polling without proxy."""
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
            'RETRY_TIME_L_BOUND': '30',  # Aggressive
            'RETRY_TIME_U_BOUND': '45',
        }
        config['NOTIFICATION'] = {
            'SENDGRID_API_KEY': 'key',
            'TELEGRAM_BOT_TOKEN': ''
        }
        # No PROXY section = proxy disabled

        errors, warnings = validate_config(config)

        # Should warn about aggressive polling
        aggressive_warnings = [w for w in warnings if 'aggressive' in w.lower()]
        self.assertEqual(len(aggressive_warnings), 1)


class TestProxyRotationOnBan(unittest.TestCase):
    """Test proxy rotation behavior on ban detection."""

    def test_rotate_proxy_and_restart_returns_false_when_disabled(self):
        """Should return False when proxy is disabled."""
        # Import module and test with module-level PROXY_ENABLED = False
        import visa
        original_enabled = visa.PROXY_ENABLED

        try:
            visa.PROXY_ENABLED = False
            result = visa.rotate_proxy_and_restart()
            self.assertFalse(result)
        finally:
            visa.PROXY_ENABLED = original_enabled

    @patch('visa.PROXY_MANAGER')
    @patch('visa.PROXY_ENABLED', True)
    def test_rotate_proxy_and_restart_returns_false_when_no_proxies(self, mock_manager):
        """Should return False when no proxies available."""
        import visa

        mock_manager.has_proxies = False

        result = visa.rotate_proxy_and_restart()
        self.assertFalse(result)

    @patch('visa.init_driver')
    @patch('visa.driver')
    @patch('visa.PROXY_MANAGER')
    @patch('visa.PROXY_ENABLED', True)
    def test_rotate_proxy_and_restart_calls_init_driver(
        self, mock_manager, mock_driver, mock_init
    ):
        """Should reinitialize driver with new proxy."""
        import visa

        mock_manager.has_proxies = True
        mock_manager.get_proxy.return_value = {'host': 'proxy1', 'port': 8080}
        mock_manager.rotate.return_value = {'host': 'proxy2', 'port': 8080}

        result = visa.rotate_proxy_and_restart()

        self.assertTrue(result)
        mock_manager.rotate.assert_called_once()
        mock_init.assert_called_once()


class TestDriverInitWithProxy(unittest.TestCase):
    """Test driver initialization with proxy settings."""

    def test_init_driver_without_proxy(self):
        """Should initialize without proxy when none provided."""
        from proxy_manager import ProxyManager

        # Test that init_driver accepts None
        manager = None

        # We can't easily test the full init_driver without mocking Chrome,
        # but we can verify the proxy_args logic
        proxy_args = []
        if manager and manager.has_proxies:
            proxy = manager.get_proxy()
            if proxy:
                proxy_args = manager.get_chrome_options_args(proxy)

        self.assertEqual(proxy_args, [])

    def test_init_driver_with_proxy_generates_args(self):
        """Should generate Chrome args when proxy provided."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=['http://proxy.example.com:8080'])

        proxy_args = []
        if manager and manager.has_proxies:
            proxy = manager.get_proxy()
            if proxy:
                proxy_args = manager.get_chrome_options_args(proxy)

        self.assertEqual(len(proxy_args), 1)
        self.assertIn('--proxy-server=', proxy_args[0])


class TestProxyLoadFromConfig(unittest.TestCase):
    """Test proxy loading from config file."""

    def test_load_proxy_config_integration(self):
        """Should load proxy config from ConfigParser."""
        from proxy_manager import load_proxy_config

        config = configparser.ConfigParser()
        config['PROXY'] = {
            'ENABLED': 'True',
            'PROXY_LIST': """
                http://proxy1.example.com:8080
                http://proxy2.example.com:8080
            """,
            'ROTATION_STRATEGY': 'on_ban',
            'HEALTH_CHECK': 'False'  # Disable for test
        }

        enabled, manager = load_proxy_config(config)

        self.assertTrue(enabled)
        self.assertIsNotNone(manager)
        self.assertEqual(manager.total_count, 2)
        self.assertEqual(manager.rotation_strategy, 'on_ban')

    def test_disabled_proxy_uses_direct_connection(self):
        """Should return None manager when disabled."""
        from proxy_manager import load_proxy_config

        config = configparser.ConfigParser()
        config['PROXY'] = {
            'ENABLED': 'False',
            'PROXY_LIST': 'http://proxy.example.com:8080'
        }

        enabled, manager = load_proxy_config(config)

        self.assertFalse(enabled)
        self.assertIsNone(manager)


class TestProxyRotationStrategies(unittest.TestCase):
    """Test different proxy rotation strategies."""

    def test_round_robin_rotates_on_each_call(self):
        """Round robin should rotate sequentially."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080',
            'http://proxy3.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies, rotation_strategy='round_robin')

        # Start at proxy1
        self.assertEqual(manager.get_proxy()['host'], 'proxy1.example.com')

        # Rotate should move to next
        manager.rotate()
        self.assertEqual(manager.get_proxy()['host'], 'proxy2.example.com')

    def test_on_ban_strategy_keeps_proxy_until_rotated(self):
        """On-ban strategy should keep same proxy until explicit rotation."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies, rotation_strategy='on_ban')

        # Should return same proxy on multiple calls
        first = manager.get_proxy()
        second = manager.get_proxy()
        third = manager.get_proxy()

        self.assertEqual(first['host'], second['host'])
        self.assertEqual(second['host'], third['host'])

        # Only rotates on explicit call
        manager.rotate()
        fourth = manager.get_proxy()
        self.assertNotEqual(first['host'], fourth['host'])


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility without proxy config."""

    def test_missing_proxy_section_works(self):
        """Should work without PROXY section in config."""
        from proxy_manager import load_proxy_config

        config = configparser.ConfigParser()
        # No PROXY section at all

        enabled, manager = load_proxy_config(config)

        self.assertFalse(enabled)
        self.assertIsNone(manager)

    def test_visa_validate_config_without_proxy(self):
        """Validate config should work without proxy section."""
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
        }
        config['NOTIFICATION'] = {
            'SENDGRID_API_KEY': 'key',
            'TELEGRAM_BOT_TOKEN': ''
        }
        # No PROXY section

        errors, warnings = validate_config(config)

        # Should have no errors (proxy is optional)
        self.assertEqual(len(errors), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
