"""
Proxy Manager for US Visa Scheduler

Handles proxy rotation, health checking, and failover for avoiding IP bans.
"""

import random
import re
import requests
from urllib.parse import urlparse


class ProxyManager:
    """
    Manages a pool of proxies with rotation and health checking.

    Supports rotation strategies:
    - round_robin: Cycle through proxies sequentially
    - random: Select random proxy each time
    - on_ban: Only rotate when current proxy is banned
    """

    # Proxy format regex: protocol://[user:pass@]host:port
    PROXY_PATTERN = re.compile(
        r'^(?P<protocol>https?|socks[45]?)://'
        r'(?:(?P<user>[^:@]+):(?P<pass>[^@]+)@)?'
        r'(?P<host>[^:]+):(?P<port>\d+)$'
    )

    def __init__(self, proxy_list=None, rotation_strategy='round_robin'):
        """
        Initialize proxy manager.

        Args:
            proxy_list: List of proxy URLs or path to file containing proxies
            rotation_strategy: 'round_robin', 'random', or 'on_ban'
        """
        self.rotation_strategy = rotation_strategy
        self.proxies = []
        self.failed_proxies = set()
        self.current_index = 0

        if proxy_list:
            self._load_proxies(proxy_list)

    def _load_proxies(self, proxy_list):
        """Load proxies from list or file."""
        if isinstance(proxy_list, str):
            # Could be a file path or single proxy
            if '\n' in proxy_list or proxy_list.startswith('http') or proxy_list.startswith('socks'):
                # Multi-line string or single proxy URL
                lines = proxy_list.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parsed = self._parse_proxy(line)
                        if parsed:
                            self.proxies.append(parsed)
            else:
                # Assume file path
                try:
                    with open(proxy_list, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                parsed = self._parse_proxy(line)
                                if parsed:
                                    self.proxies.append(parsed)
                except FileNotFoundError:
                    # Maybe it's a single proxy URL without protocol
                    pass
        elif isinstance(proxy_list, list):
            for proxy in proxy_list:
                parsed = self._parse_proxy(proxy)
                if parsed:
                    self.proxies.append(parsed)

    def _parse_proxy(self, proxy_url):
        """
        Parse proxy URL into components.

        Args:
            proxy_url: Proxy URL string (e.g., 'http://user:pass@host:port')

        Returns:
            Dict with proxy components or None if invalid
        """
        proxy_url = proxy_url.strip()
        if not proxy_url:
            return None

        match = self.PROXY_PATTERN.match(proxy_url)
        if not match:
            return None

        return {
            'url': proxy_url,
            'protocol': match.group('protocol'),
            'host': match.group('host'),
            'port': int(match.group('port')),
            'user': match.group('user'),
            'password': match.group('pass')
        }

    def get_proxy(self):
        """
        Get the current proxy for use.

        Returns:
            Dict with proxy info or None if no proxies available
        """
        available = self._get_available_proxies()
        if not available:
            return None

        if self.current_index >= len(available):
            self.current_index = 0

        return available[self.current_index]

    def _get_available_proxies(self):
        """Get list of proxies that haven't failed."""
        return [p for p in self.proxies if p['url'] not in self.failed_proxies]

    def rotate(self):
        """
        Rotate to next proxy based on strategy.

        Returns:
            New proxy dict or None if no proxies available
        """
        available = self._get_available_proxies()
        if not available:
            return None

        if self.rotation_strategy == 'random':
            self.current_index = random.randint(0, len(available) - 1)
        else:
            # round_robin and on_ban both use sequential rotation
            self.current_index = (self.current_index + 1) % len(available)

        return self.get_proxy()

    def mark_failed(self, proxy):
        """
        Mark a proxy as failed (won't be used again this session).

        Args:
            proxy: Proxy dict or URL string
        """
        if isinstance(proxy, dict):
            proxy_url = proxy.get('url')
        else:
            proxy_url = proxy

        if proxy_url:
            self.failed_proxies.add(proxy_url)

        # Adjust current index if needed
        available = self._get_available_proxies()
        if available and self.current_index >= len(available):
            self.current_index = 0

    def reset_failed(self):
        """Reset all failed proxies (allow retry)."""
        self.failed_proxies.clear()

    def health_check(self, proxy=None, timeout=10):
        """
        Check if a proxy is working.

        Args:
            proxy: Proxy dict to check (uses current if None)
            timeout: Request timeout in seconds

        Returns:
            True if proxy is healthy, False otherwise
        """
        if proxy is None:
            proxy = self.get_proxy()

        if proxy is None:
            return False

        proxy_url = proxy['url']

        # Format proxy for requests library
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }

        try:
            # Test against a reliable endpoint
            response = requests.get(
                'https://httpbin.org/ip',
                proxies=proxies,
                timeout=timeout
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_chrome_options_args(self, proxy=None):
        """
        Get Chrome options arguments for proxy.

        Args:
            proxy: Proxy dict (uses current if None)

        Returns:
            List of Chrome option arguments
        """
        if proxy is None:
            proxy = self.get_proxy()

        if proxy is None:
            return []

        args = []

        # Basic proxy argument
        proxy_url = proxy['url']
        args.append(f'--proxy-server={proxy_url}')

        return args

    def get_selenium_proxy(self, proxy=None):
        """
        Get proxy configuration for Selenium.

        Args:
            proxy: Proxy dict (uses current if None)

        Returns:
            Dict suitable for Selenium wire or None
        """
        if proxy is None:
            proxy = self.get_proxy()

        if proxy is None:
            return None

        return {
            'http': proxy['url'],
            'https': proxy['url'],
            'no_proxy': 'localhost,127.0.0.1'
        }

    @property
    def has_proxies(self):
        """Check if any proxies are configured."""
        return len(self.proxies) > 0

    @property
    def available_count(self):
        """Get count of available (non-failed) proxies."""
        return len(self._get_available_proxies())

    @property
    def total_count(self):
        """Get total count of configured proxies."""
        return len(self.proxies)

    def __repr__(self):
        return f"ProxyManager(total={self.total_count}, available={self.available_count}, strategy={self.rotation_strategy})"


def load_proxy_config(config):
    """
    Load proxy configuration from ConfigParser.

    Args:
        config: ConfigParser object

    Returns:
        Tuple of (enabled, ProxyManager or None)
    """
    if 'PROXY' not in config:
        return False, None

    proxy_section = config['PROXY']
    enabled = proxy_section.getboolean('ENABLED', False)

    if not enabled:
        return False, None

    # Load proxy list
    proxy_list_raw = proxy_section.get('PROXY_LIST', '').strip()
    if not proxy_list_raw:
        return False, None

    # Parse rotation strategy
    strategy = proxy_section.get('ROTATION_STRATEGY', 'round_robin').lower()
    if strategy not in ('round_robin', 'random', 'on_ban'):
        strategy = 'round_robin'

    # Create manager
    manager = ProxyManager(
        proxy_list=proxy_list_raw,
        rotation_strategy=strategy
    )

    # Health check if enabled
    health_check = proxy_section.getboolean('HEALTH_CHECK', True)
    if health_check and manager.has_proxies:
        # Check first proxy
        if not manager.health_check():
            print(f"[PROXY] Warning: Initial proxy health check failed")

    return True, manager
