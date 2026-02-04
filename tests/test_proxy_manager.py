"""
Unit tests for proxy manager module.

Tests proxy parsing, rotation strategies, health checking, and failover.
"""

import unittest
from unittest.mock import patch, MagicMock
import configparser
import json
import sys
import os
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestProxyManagerInitialization(unittest.TestCase):
    """Test ProxyManager initialization and proxy loading."""

    def test_initialization_with_list(self):
        """Should initialize with a list of proxy URLs."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080',
            'http://proxy3.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies)

        self.assertEqual(manager.total_count, 3)
        self.assertEqual(manager.available_count, 3)

    def test_initialization_with_multiline_string(self):
        """Should parse multi-line proxy string."""
        from proxy_manager import ProxyManager

        proxy_string = """
        http://proxy1.example.com:8080
        http://proxy2.example.com:8080
        # This is a comment
        http://proxy3.example.com:8080
        """
        manager = ProxyManager(proxy_list=proxy_string)

        self.assertEqual(manager.total_count, 3)

    def test_initialization_empty(self):
        """Should handle empty proxy list."""
        from proxy_manager import ProxyManager

        manager = ProxyManager()

        self.assertEqual(manager.total_count, 0)
        self.assertFalse(manager.has_proxies)

    def test_initialization_with_auth(self):
        """Should parse proxies with authentication."""
        from proxy_manager import ProxyManager

        proxies = ['http://user:pass@proxy.example.com:8080']
        manager = ProxyManager(proxy_list=proxies)

        proxy = manager.get_proxy()
        self.assertEqual(proxy['user'], 'user')
        self.assertEqual(proxy['password'], 'pass')
        self.assertEqual(proxy['host'], 'proxy.example.com')
        self.assertEqual(proxy['port'], 8080)


class TestProxyFormatParsing(unittest.TestCase):
    """Test various proxy URL format parsing."""

    def test_http_proxy(self):
        """Should parse HTTP proxy."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=['http://host:8080'])
        proxy = manager.get_proxy()

        self.assertEqual(proxy['protocol'], 'http')
        self.assertEqual(proxy['host'], 'host')
        self.assertEqual(proxy['port'], 8080)

    def test_https_proxy(self):
        """Should parse HTTPS proxy."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=['https://host:8443'])
        proxy = manager.get_proxy()

        self.assertEqual(proxy['protocol'], 'https')
        self.assertEqual(proxy['port'], 8443)

    def test_socks5_proxy(self):
        """Should parse SOCKS5 proxy."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=['socks5://host:1080'])
        proxy = manager.get_proxy()

        self.assertEqual(proxy['protocol'], 'socks5')

    def test_socks4_proxy(self):
        """Should parse SOCKS4 proxy."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=['socks4://host:1080'])
        proxy = manager.get_proxy()

        self.assertEqual(proxy['protocol'], 'socks4')

    def test_proxy_with_auth(self):
        """Should parse proxy with user:pass authentication."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=['http://myuser:mypass@proxy.com:3128'])
        proxy = manager.get_proxy()

        self.assertEqual(proxy['user'], 'myuser')
        self.assertEqual(proxy['password'], 'mypass')

    def test_invalid_proxy_format_ignored(self):
        """Should ignore invalid proxy formats."""
        from proxy_manager import ProxyManager

        proxies = [
            'invalid-format',
            'http://valid:8080',
            'ftp://invalid:21',  # ftp not supported
            'http://also-valid:8080'
        ]
        manager = ProxyManager(proxy_list=proxies)

        # Only the 2 valid HTTP proxies should be loaded
        self.assertEqual(manager.total_count, 2)


class TestRoundRobinRotation(unittest.TestCase):
    """Test round-robin rotation strategy."""

    def test_round_robin_sequence(self):
        """Should rotate through proxies sequentially."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080',
            'http://proxy3.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies, rotation_strategy='round_robin', state_file='')

        # Initial proxy
        self.assertEqual(manager.get_proxy()['host'], 'proxy1.example.com')

        # Rotate through sequence
        manager.rotate()
        self.assertEqual(manager.get_proxy()['host'], 'proxy2.example.com')

        manager.rotate()
        self.assertEqual(manager.get_proxy()['host'], 'proxy3.example.com')

        # Should wrap around
        manager.rotate()
        self.assertEqual(manager.get_proxy()['host'], 'proxy1.example.com')

        manager.rotate()
        self.assertEqual(manager.get_proxy()['host'], 'proxy2.example.com')

    def test_round_robin_wrap_around(self):
        """Should wrap around after reaching end."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies, rotation_strategy='round_robin', state_file='')

        # Rotate 5 times with 2 proxies
        sequence = []
        for _ in range(5):
            manager.rotate()
            sequence.append(manager.get_proxy()['host'])

        # Expected: 2, 1, 2, 1, 2 (starts at 0, rotates to 1, then wraps)
        self.assertEqual(sequence, [
            'proxy2.example.com',
            'proxy1.example.com',
            'proxy2.example.com',
            'proxy1.example.com',
            'proxy2.example.com'
        ])


class TestRandomRotation(unittest.TestCase):
    """Test random rotation strategy."""

    def test_random_selection(self):
        """Should select proxies randomly."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080',
            'http://proxy3.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies, rotation_strategy='random')

        # Collect selections over many rotations
        selections = set()
        for _ in range(50):
            manager.rotate()
            selections.add(manager.get_proxy()['host'])

        # With 50 rotations and 3 proxies, statistically all should be selected
        self.assertEqual(len(selections), 3)


class TestMarkFailed(unittest.TestCase):
    """Test proxy failure marking."""

    def test_mark_failed_removes_from_available(self):
        """Marking proxy as failed should remove from rotation."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080',
            'http://proxy3.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies)

        self.assertEqual(manager.available_count, 3)

        # Mark first proxy as failed
        manager.mark_failed(manager.get_proxy())

        self.assertEqual(manager.available_count, 2)
        self.assertEqual(manager.total_count, 3)  # Total unchanged

    def test_mark_failed_by_url(self):
        """Should mark failed by URL string."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies)

        manager.mark_failed('http://proxy1.example.com:8080')

        self.assertEqual(manager.available_count, 1)

    def test_all_proxies_failed(self):
        """Should handle all proxies failing."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies)

        manager.mark_failed(proxies[0])
        manager.mark_failed(proxies[1])

        self.assertEqual(manager.available_count, 0)
        self.assertIsNone(manager.get_proxy())
        self.assertIsNone(manager.rotate())

    def test_reset_failed(self):
        """Should reset failed proxies."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies)

        manager.mark_failed(proxies[0])
        manager.mark_failed(proxies[1])
        self.assertEqual(manager.available_count, 0)

        manager.reset_failed()
        self.assertEqual(manager.available_count, 2)


class TestHealthCheck(unittest.TestCase):
    """Test proxy health checking."""

    @patch('proxy_manager.requests.get')
    def test_health_check_pass(self, mock_get):
        """Should return True for healthy proxy."""
        from proxy_manager import ProxyManager

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        manager = ProxyManager(proxy_list=['http://proxy.example.com:8080'])
        result = manager.health_check()

        self.assertTrue(result)
        mock_get.assert_called_once()

    @patch('proxy_manager.requests.get')
    def test_health_check_fail_status(self, mock_get):
        """Should return False for non-200 response."""
        from proxy_manager import ProxyManager

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        manager = ProxyManager(proxy_list=['http://proxy.example.com:8080'])
        result = manager.health_check()

        self.assertFalse(result)

    @patch('proxy_manager.requests.get')
    def test_health_check_fail_exception(self, mock_get):
        """Should return False on connection error."""
        from proxy_manager import ProxyManager

        mock_get.side_effect = Exception("Connection refused")

        manager = ProxyManager(proxy_list=['http://proxy.example.com:8080'])
        result = manager.health_check()

        self.assertFalse(result)

    def test_health_check_no_proxy(self):
        """Should return False when no proxies available."""
        from proxy_manager import ProxyManager

        manager = ProxyManager()
        result = manager.health_check()

        self.assertFalse(result)


class TestChromeOptionsGeneration(unittest.TestCase):
    """Test Chrome options argument generation."""

    def test_get_chrome_options_args(self):
        """Should generate correct Chrome arguments."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=['http://proxy.example.com:8080'])
        args = manager.get_chrome_options_args()

        self.assertEqual(len(args), 1)
        self.assertIn('--proxy-server=', args[0])
        self.assertIn('proxy.example.com:8080', args[0])

    def test_get_chrome_options_no_proxy(self):
        """Should return empty list when no proxy."""
        from proxy_manager import ProxyManager

        manager = ProxyManager()
        args = manager.get_chrome_options_args()

        self.assertEqual(args, [])


class TestSeleniumProxyConfig(unittest.TestCase):
    """Test Selenium proxy configuration generation."""

    def test_get_selenium_proxy(self):
        """Should generate Selenium proxy config."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=['http://proxy.example.com:8080'])
        config = manager.get_selenium_proxy()

        self.assertEqual(config['http'], 'http://proxy.example.com:8080')
        self.assertEqual(config['https'], 'http://proxy.example.com:8080')
        self.assertIn('localhost', config['no_proxy'])

    def test_get_selenium_proxy_none(self):
        """Should return None when no proxy."""
        from proxy_manager import ProxyManager

        manager = ProxyManager()
        config = manager.get_selenium_proxy()

        self.assertIsNone(config)


class TestConfigLoading(unittest.TestCase):
    """Test loading proxy configuration from ConfigParser."""

    def test_load_proxy_config_enabled(self):
        """Should load enabled proxy config."""
        from proxy_manager import load_proxy_config

        config = configparser.ConfigParser()
        config['PROXY'] = {
            'ENABLED': 'True',
            'PROXY_LIST': 'http://proxy1.example.com:8080\nhttp://proxy2.example.com:8080',
            'ROTATION_STRATEGY': 'round_robin',
            'HEALTH_CHECK': 'False'  # Disable for test
        }

        enabled, manager = load_proxy_config(config)

        self.assertTrue(enabled)
        self.assertIsNotNone(manager)
        self.assertEqual(manager.total_count, 2)
        self.assertEqual(manager.rotation_strategy, 'round_robin')

    def test_load_proxy_config_disabled(self):
        """Should return None when disabled."""
        from proxy_manager import load_proxy_config

        config = configparser.ConfigParser()
        config['PROXY'] = {
            'ENABLED': 'False',
            'PROXY_LIST': 'http://proxy.example.com:8080'
        }

        enabled, manager = load_proxy_config(config)

        self.assertFalse(enabled)
        self.assertIsNone(manager)

    def test_load_proxy_config_missing_section(self):
        """Should return None when no PROXY section."""
        from proxy_manager import load_proxy_config

        config = configparser.ConfigParser()

        enabled, manager = load_proxy_config(config)

        self.assertFalse(enabled)
        self.assertIsNone(manager)

    def test_load_proxy_config_empty_list(self):
        """Should return None when proxy list is empty."""
        from proxy_manager import load_proxy_config

        config = configparser.ConfigParser()
        config['PROXY'] = {
            'ENABLED': 'True',
            'PROXY_LIST': ''
        }

        enabled, manager = load_proxy_config(config)

        self.assertFalse(enabled)
        self.assertIsNone(manager)

    def test_load_proxy_config_invalid_strategy_defaults(self):
        """Should use default strategy for invalid value."""
        from proxy_manager import load_proxy_config

        config = configparser.ConfigParser()
        config['PROXY'] = {
            'ENABLED': 'True',
            'PROXY_LIST': 'http://proxy.example.com:8080',
            'ROTATION_STRATEGY': 'invalid_strategy',
            'HEALTH_CHECK': 'False'
        }

        enabled, manager = load_proxy_config(config)

        self.assertTrue(enabled)
        self.assertEqual(manager.rotation_strategy, 'round_robin')


class TestDriverIntegration(unittest.TestCase):
    """Test integration with Chrome driver."""

    def test_proxy_with_rotation_on_ban(self):
        """Should rotate only on ban with on_ban strategy."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080'
        ]
        manager = ProxyManager(proxy_list=proxies, rotation_strategy='on_ban')

        # Get same proxy multiple times (no automatic rotation)
        first = manager.get_proxy()
        second = manager.get_proxy()

        self.assertEqual(first['host'], second['host'])

        # Only rotates when explicitly called
        manager.rotate()
        third = manager.get_proxy()

        self.assertNotEqual(first['host'], third['host'])


class TestProxyFormatValidation(unittest.TestCase):
    """Test proxy URL format validation and common mistakes."""

    def test_missing_protocol_rejected(self):
        """Proxy without protocol prefix should be rejected."""
        from proxy_manager import ProxyManager

        # Common mistake: missing http://
        manager = ProxyManager(proxy_list=['proxy.example.com:8080'])
        self.assertEqual(manager.total_count, 0)
        self.assertFalse(manager.has_proxies)

    def test_missing_port_rejected(self):
        """Proxy without port should be rejected."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=['http://proxy.example.com'])
        self.assertEqual(manager.total_count, 0)

    def test_brightdata_format_valid(self):
        """Bright Data proxy format should be valid."""
        from proxy_manager import ProxyManager

        # Typical Bright Data format
        proxy = 'http://brd-customer-xxx-zone-residential:password@brd.superproxy.io:33335'
        manager = ProxyManager(proxy_list=[proxy])

        self.assertEqual(manager.total_count, 1)
        self.assertTrue(manager.has_proxies)

        current = manager.get_proxy()
        self.assertEqual(current['host'], 'brd.superproxy.io')
        self.assertEqual(current['port'], 33335)
        self.assertEqual(current['user'], 'brd-customer-xxx-zone-residential')
        self.assertEqual(current['password'], 'password')

    def test_special_chars_in_password(self):
        """Password with special characters should work."""
        from proxy_manager import ProxyManager

        # Password with special chars (URL encoded)
        proxy = 'http://user:p%40ssw0rd@proxy.example.com:8080'
        manager = ProxyManager(proxy_list=[proxy])

        self.assertEqual(manager.total_count, 1)
        current = manager.get_proxy()
        self.assertEqual(current['password'], 'p%40ssw0rd')

    def test_ipv4_address_valid(self):
        """IPv4 address as host should be valid."""
        from proxy_manager import ProxyManager

        proxy = 'http://192.168.1.100:8080'
        manager = ProxyManager(proxy_list=[proxy])

        self.assertEqual(manager.total_count, 1)
        self.assertEqual(manager.get_proxy()['host'], '192.168.1.100')

    def test_socks5_with_auth(self):
        """SOCKS5 proxy with authentication should work."""
        from proxy_manager import ProxyManager

        proxy = 'socks5://user:pass@socks.example.com:1080'
        manager = ProxyManager(proxy_list=[proxy])

        self.assertEqual(manager.total_count, 1)
        current = manager.get_proxy()
        self.assertEqual(current['protocol'], 'socks5')
        self.assertEqual(current['user'], 'user')


class TestProxyVerification(unittest.TestCase):
    """Test proxy setup verification utilities."""

    def test_verify_proxy_config_complete(self):
        """Complete proxy config should pass verification."""
        from proxy_manager import ProxyManager

        proxies = ['http://user:pass@proxy.example.com:8080']
        manager = ProxyManager(proxy_list=proxies, rotation_strategy='on_ban')

        # Verify all required attributes
        self.assertTrue(manager.has_proxies)
        self.assertEqual(manager.total_count, 1)
        self.assertEqual(manager.available_count, 1)
        self.assertEqual(manager.rotation_strategy, 'on_ban')

        # Verify proxy details
        proxy = manager.get_proxy()
        self.assertIsNotNone(proxy)
        self.assertIn('host', proxy)
        self.assertIn('port', proxy)
        self.assertIn('protocol', proxy)
        self.assertIn('user', proxy)
        self.assertIn('password', proxy)

        # Authenticated proxies use extension, not chrome args
        self.assertTrue(manager.requires_auth_extension(proxy))
        args = manager.get_chrome_options_args(proxy)
        self.assertEqual(len(args), 0)  # Empty because auth proxies use extension

    def test_verify_unauthenticated_proxy_uses_args(self):
        """Unauthenticated proxy should use chrome args."""
        from proxy_manager import ProxyManager

        proxies = ['http://proxy.example.com:8080']
        manager = ProxyManager(proxy_list=proxies)

        proxy = manager.get_proxy()
        self.assertFalse(manager.requires_auth_extension(proxy))

        args = manager.get_chrome_options_args(proxy)
        self.assertEqual(len(args), 1)
        self.assertTrue(args[0].startswith('--proxy-server='))

    def test_create_auth_extension(self):
        """Should create auth extension for authenticated proxy."""
        from proxy_manager import ProxyManager
        import os

        proxies = ['http://user:pass@proxy.example.com:8080']
        manager = ProxyManager(proxy_list=proxies)

        proxy = manager.get_proxy()
        ext_path = manager.create_proxy_auth_extension(proxy)

        self.assertIsNotNone(ext_path)
        self.assertTrue(os.path.exists(ext_path))
        self.assertTrue(ext_path.endswith('.zip'))

        # Cleanup
        os.unlink(ext_path)
        os.rmdir(os.path.dirname(ext_path))

    def test_verify_empty_config(self):
        """Empty proxy config should be handled gracefully."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(proxy_list=[])

        self.assertFalse(manager.has_proxies)
        self.assertEqual(manager.total_count, 0)
        self.assertIsNone(manager.get_proxy())
        self.assertEqual(manager.get_chrome_options_args(), [])

    def test_verify_config_from_file(self):
        """Verify loading proxy config from config file."""
        from proxy_manager import load_proxy_config
        import configparser
        import os

        # Check if real config.ini exists
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config.ini'
        )

        if not os.path.exists(config_path):
            self.skipTest("config.ini not found")

        config = configparser.ConfigParser()
        config.read(config_path)

        enabled, manager = load_proxy_config(config)

        # Just verify it loads without error
        if enabled:
            self.assertIsNotNone(manager)
            self.assertGreaterEqual(manager.total_count, 0)
        else:
            # Disabled is also valid
            self.assertTrue(True)

    def test_multiple_proxies_all_valid(self):
        """All valid proxies should be loaded."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://proxy1.example.com:8080',
            'http://user:pass@proxy2.example.com:8080',
            'socks5://proxy3.example.com:1080',
            'https://proxy4.example.com:443'
        ]
        manager = ProxyManager(proxy_list=proxies)

        self.assertEqual(manager.total_count, 4)
        self.assertEqual(manager.available_count, 4)

    def test_mixed_valid_invalid_proxies(self):
        """Only valid proxies should be loaded from mixed list."""
        from proxy_manager import ProxyManager

        proxies = [
            'http://valid1.example.com:8080',  # Valid
            'invalid-no-protocol:8080',         # Invalid - no protocol
            'http://valid2.example.com:8080',  # Valid
            'ftp://invalid.example.com:21',     # Invalid - unsupported protocol
            'socks5://valid3.example.com:1080' # Valid
        ]
        manager = ProxyManager(proxy_list=proxies)

        self.assertEqual(manager.total_count, 3)


class TestProxyStatePersistence(unittest.TestCase):
    """Test proxy state persistence for round_robin strategy."""

    def setUp(self):
        """Create temporary directory for state files."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, '.proxy_state.json')
        self.proxies = [
            'http://proxy1.example.com:8080',
            'http://proxy2.example.com:8080',
            'http://proxy3.example.com:8080',
        ]

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_state_creates_file(self):
        """Saving state should create the state file."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(
            proxy_list=self.proxies,
            rotation_strategy='round_robin',
            state_file=self.state_file
        )
        manager.current_index = 2
        manager._save_state()

        self.assertTrue(os.path.exists(self.state_file))
        with open(self.state_file, 'r') as f:
            state = json.load(f)
        self.assertEqual(state['current_index'], 2)

    def test_load_state_restores_index(self):
        """Loading state should restore the saved index."""
        from proxy_manager import ProxyManager

        # Create state file with index 1
        with open(self.state_file, 'w') as f:
            json.dump({'current_index': 1}, f)

        manager = ProxyManager(
            proxy_list=self.proxies,
            rotation_strategy='round_robin',
            state_file=self.state_file
        )

        self.assertEqual(manager.current_index, 1)

    def test_round_robin_uses_persisted_index(self):
        """Round robin strategy should start from persisted index."""
        from proxy_manager import ProxyManager

        # Create state file with index 2
        with open(self.state_file, 'w') as f:
            json.dump({'current_index': 2}, f)

        manager = ProxyManager(
            proxy_list=self.proxies,
            rotation_strategy='round_robin',
            state_file=self.state_file
        )

        # Should start at index 2 (proxy3)
        proxy = manager.get_proxy()
        self.assertEqual(proxy['host'], 'proxy3.example.com')

    def test_random_strategy_ignores_persisted_index(self):
        """Random strategy should not load persisted index."""
        from proxy_manager import ProxyManager

        # Create state file with index 2
        with open(self.state_file, 'w') as f:
            json.dump({'current_index': 2}, f)

        manager = ProxyManager(
            proxy_list=self.proxies,
            rotation_strategy='random',
            state_file=self.state_file
        )

        # Random strategy should start from 0 (not load persisted)
        self.assertEqual(manager.current_index, 0)

    def test_on_ban_strategy_uses_persisted_index(self):
        """On ban strategy should start from persisted index."""
        from proxy_manager import ProxyManager

        # Create state file with index 1
        with open(self.state_file, 'w') as f:
            json.dump({'current_index': 1}, f)

        manager = ProxyManager(
            proxy_list=self.proxies,
            rotation_strategy='on_ban',
            state_file=self.state_file
        )

        self.assertEqual(manager.current_index, 1)

    def test_invalid_state_file_defaults_to_zero(self):
        """Invalid state file should default to index 0."""
        from proxy_manager import ProxyManager

        # Create invalid JSON file
        with open(self.state_file, 'w') as f:
            f.write('not valid json')

        manager = ProxyManager(
            proxy_list=self.proxies,
            rotation_strategy='round_robin',
            state_file=self.state_file
        )

        self.assertEqual(manager.current_index, 0)

    def test_rotate_saves_state(self):
        """Each rotation should save the new index."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(
            proxy_list=self.proxies,
            rotation_strategy='round_robin',
            state_file=self.state_file
        )

        # Rotate and verify state is saved
        manager.rotate()
        with open(self.state_file, 'r') as f:
            state = json.load(f)
        self.assertEqual(state['current_index'], 1)

        manager.rotate()
        with open(self.state_file, 'r') as f:
            state = json.load(f)
        self.assertEqual(state['current_index'], 2)

    def test_state_file_directory_created(self):
        """State file directory should be created if it doesn't exist."""
        from proxy_manager import ProxyManager

        nested_state_file = os.path.join(self.temp_dir, 'nested', 'dir', '.proxy_state.json')
        manager = ProxyManager(
            proxy_list=self.proxies,
            rotation_strategy='round_robin',
            state_file=nested_state_file
        )

        manager.rotate()
        self.assertTrue(os.path.exists(nested_state_file))

    def test_index_wraps_when_proxy_list_shrinks(self):
        """Index should wrap if it exceeds the new proxy list size."""
        from proxy_manager import ProxyManager

        # Create state file with index 5 (larger than proxy list)
        with open(self.state_file, 'w') as f:
            json.dump({'current_index': 5}, f)

        manager = ProxyManager(
            proxy_list=self.proxies,  # Only 3 proxies
            rotation_strategy='round_robin',
            state_file=self.state_file
        )

        # Index 5 % 3 = 2
        self.assertEqual(manager.current_index, 2)

    def test_no_state_file_starts_at_zero(self):
        """Without state file, should start at index 0."""
        from proxy_manager import ProxyManager

        nonexistent_file = os.path.join(self.temp_dir, 'nonexistent.json')
        manager = ProxyManager(
            proxy_list=self.proxies,
            rotation_strategy='round_robin',
            state_file=nonexistent_file
        )

        self.assertEqual(manager.current_index, 0)

    def test_state_file_none_disables_persistence(self):
        """Setting state_file to empty string disables persistence."""
        from proxy_manager import ProxyManager

        manager = ProxyManager(
            proxy_list=self.proxies,
            rotation_strategy='round_robin',
            state_file=''
        )

        manager.rotate()
        # Should not create any state file
        self.assertFalse(os.path.exists(self.state_file))


if __name__ == '__main__':
    unittest.main(verbosity=2)
