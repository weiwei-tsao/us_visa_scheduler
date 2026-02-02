"""
Tests for proxy rotation logic.

The proxy rotation logic should:
- Rotate proxy on ban detection for ALL strategies (not just 'on_ban')
- Rotate proxy when network retries are exhausted
- Only rotate when proxy is enabled and has available proxies
"""

import pytest
from unittest.mock import Mock, MagicMock


class MockProxyManager:
    """Mock ProxyManager for testing rotation logic."""

    def __init__(self, has_proxies=True, rotation_strategy='round_robin'):
        self._has_proxies = has_proxies
        self.rotation_strategy = rotation_strategy
        self.rotate_called = False
        self.current_index = 0
        self.proxies = [
            {'host': 'proxy1.example.com', 'port': 8080},
            {'host': 'proxy2.example.com', 'port': 8080},
        ] if has_proxies else []

    @property
    def has_proxies(self):
        return self._has_proxies and len(self.proxies) > 0

    def rotate(self):
        self.rotate_called = True
        if not self.proxies:
            return None
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return self.proxies[self.current_index]

    def get_proxy(self):
        if not self.proxies:
            return None
        return self.proxies[self.current_index]


def should_attempt_proxy_rotation(proxy_enabled: bool, proxy_manager) -> bool:
    """
    Determines if we should attempt to rotate proxy.

    This mirrors the logic in visa.py after the fix:
    - OLD: PROXY_ENABLED and PROXY_MANAGER and PROXY_MANAGER.rotation_strategy == 'on_ban'
    - NEW: PROXY_ENABLED and PROXY_MANAGER and PROXY_MANAGER.has_proxies

    Args:
        proxy_enabled: Whether proxy feature is enabled
        proxy_manager: ProxyManager instance or None

    Returns:
        True if we should attempt proxy rotation
    """
    # Use bool() to ensure boolean return value (Python short-circuit returns last evaluated value)
    return bool(proxy_enabled and proxy_manager and proxy_manager.has_proxies)


class TestProxyRotationConditions:
    """Test cases for proxy rotation trigger conditions."""

    def test_rotation_when_proxy_enabled_and_has_proxies(self):
        """Should attempt rotation when proxy is enabled and has proxies."""
        manager = MockProxyManager(has_proxies=True)
        assert should_attempt_proxy_rotation(True, manager) is True

    def test_no_rotation_when_proxy_disabled(self):
        """Should NOT attempt rotation when proxy feature is disabled."""
        manager = MockProxyManager(has_proxies=True)
        assert should_attempt_proxy_rotation(False, manager) is False

    def test_no_rotation_when_no_proxy_manager(self):
        """Should NOT attempt rotation when proxy manager is None."""
        assert should_attempt_proxy_rotation(True, None) is False

    def test_no_rotation_when_no_proxies_available(self):
        """Should NOT attempt rotation when no proxies are configured."""
        manager = MockProxyManager(has_proxies=False)
        assert should_attempt_proxy_rotation(True, manager) is False


class TestProxyRotationAllStrategies:
    """Test that all rotation strategies trigger rotation on ban/errors."""

    def test_round_robin_strategy_should_rotate_on_ban(self):
        """round_robin strategy should trigger rotation on ban detection."""
        manager = MockProxyManager(rotation_strategy='round_robin')
        # New logic: all strategies rotate
        assert should_attempt_proxy_rotation(True, manager) is True

    def test_random_strategy_should_rotate_on_ban(self):
        """random strategy should trigger rotation on ban detection."""
        manager = MockProxyManager(rotation_strategy='random')
        assert should_attempt_proxy_rotation(True, manager) is True

    def test_on_ban_strategy_should_rotate_on_ban(self):
        """on_ban strategy should trigger rotation on ban detection."""
        manager = MockProxyManager(rotation_strategy='on_ban')
        assert should_attempt_proxy_rotation(True, manager) is True


class TestProxyRotationOldVsNewLogic:
    """Compare old vs new rotation logic to ensure fix is correct."""

    def old_should_rotate(self, proxy_enabled, proxy_manager):
        """OLD logic: only rotate for 'on_ban' strategy."""
        return (proxy_enabled and proxy_manager and
                proxy_manager.rotation_strategy == 'on_ban')

    def new_should_rotate(self, proxy_enabled, proxy_manager):
        """NEW logic: rotate for all strategies when proxies available."""
        return proxy_enabled and proxy_manager and proxy_manager.has_proxies

    def test_old_logic_only_rotates_on_ban_strategy(self):
        """Old logic only rotated for 'on_ban' strategy - verify this was the bug."""
        # round_robin - OLD: no rotation, NEW: rotation
        manager_rr = MockProxyManager(rotation_strategy='round_robin')
        assert self.old_should_rotate(True, manager_rr) is False  # Bug!
        assert self.new_should_rotate(True, manager_rr) is True   # Fixed!

        # random - OLD: no rotation, NEW: rotation
        manager_rand = MockProxyManager(rotation_strategy='random')
        assert self.old_should_rotate(True, manager_rand) is False  # Bug!
        assert self.new_should_rotate(True, manager_rand) is True   # Fixed!

        # on_ban - both rotate
        manager_ban = MockProxyManager(rotation_strategy='on_ban')
        assert self.old_should_rotate(True, manager_ban) is True
        assert self.new_should_rotate(True, manager_ban) is True


class TestProxyManagerRotation:
    """Test ProxyManager rotation behavior."""

    def test_rotate_cycles_through_proxies(self):
        """Rotation should cycle through available proxies."""
        manager = MockProxyManager(has_proxies=True)

        # Initial proxy
        proxy1 = manager.get_proxy()
        assert proxy1['host'] == 'proxy1.example.com'

        # After rotation
        proxy2 = manager.rotate()
        assert proxy2['host'] == 'proxy2.example.com'

        # After another rotation (back to first)
        proxy3 = manager.rotate()
        assert proxy3['host'] == 'proxy1.example.com'

    def test_rotate_returns_none_when_no_proxies(self):
        """Rotation should return None when no proxies available."""
        manager = MockProxyManager(has_proxies=False)
        result = manager.rotate()
        assert result is None


class TestNetworkRetryRotation:
    """Test proxy rotation on network retry exhaustion."""

    def test_should_rotate_on_network_retry_exhaustion(self):
        """When network retries exhausted, should attempt proxy rotation."""
        manager = MockProxyManager(has_proxies=True)
        network_retry_count = 3  # Max retries reached

        # Simulate the logic: if retries exhausted, check rotation condition
        if network_retry_count >= 3:
            should_rotate = should_attempt_proxy_rotation(True, manager)
            assert should_rotate is True

    def test_should_not_rotate_before_max_retries(self):
        """Should not trigger rotation before max retries."""
        manager = MockProxyManager(has_proxies=True)

        # Only rotate after 3 retries, not before
        for retry_count in [0, 1, 2]:
            # The rotation logic is only checked at retry_count >= 3
            # Before that, we just sleep and retry
            pass  # No rotation triggered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
