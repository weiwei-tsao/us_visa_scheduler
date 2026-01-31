"""
Shared pytest fixtures for US Visa Scheduler tests.
"""

import pytest
import tempfile
import configparser
import os
from unittest.mock import Mock, MagicMock, patch


@pytest.fixture
def temp_config_file():
    """Create a temporary config.ini file for testing."""
    config = configparser.ConfigParser()

    config['PERSONAL_INFO'] = {
        'USERNAME': 'test@example.com',
        'PASSWORD': 'test_password',
        'SCHEDULE_ID': '12345678',
        'PRIOD_START': '2026-01-01',
        'PRIOD_END': '2026-12-31',
        'YOUR_EMBASSY': 'en-ca-tor'
    }

    config['CHROMEDRIVER'] = {
        'LOCAL_USE': 'True',
        'HUB_ADDRESS': 'http://localhost:4444/wd/hub'
    }

    config['NOTIFICATION'] = {
        'SENDGRID_API_KEY': '',
        'SENDGRID_EMAIL_SENDER': '',
        'TELEGRAM_BOT_TOKEN': '',
        'TELEGRAM_CHAT_ID': ''
    }

    config['TIME'] = {
        'RETRY_TIME_L_BOUND': '60',
        'RETRY_TIME_U_BOUND': '120',
        'WORK_LIMIT_TIME': '0.75',
        'BAN_COOLDOWN_TIME': '4'
    }

    config['BEHAVIOR'] = {
        'HEADLESS': 'False',
        'STEP_DELAY': '0.5'
    }

    # Create temp file
    fd, path = tempfile.mkstemp(suffix='.ini')
    with os.fdopen(fd, 'w') as f:
        config.write(f)

    yield path

    # Cleanup
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def temp_config_with_ban_detection(temp_config_file):
    """Create config with BAN_DETECTION section."""
    config = configparser.ConfigParser()
    config.read(temp_config_file)

    config['BAN_DETECTION'] = {
        'COOLDOWN_FIRST_EMPTY': '5',
        'COOLDOWN_SECOND_EMPTY': '30',
        'COOLDOWN_THIRD_EMPTY': '120',
        'COOLDOWN_HARD_BAN': '240',
        'CHECK_SITE_STATUS': 'True'
    }

    with open(temp_config_file, 'w') as f:
        config.write(f)

    return temp_config_file


@pytest.fixture
def temp_config_with_proxy(temp_config_file):
    """Create config with PROXY section."""
    config = configparser.ConfigParser()
    config.read(temp_config_file)

    config['PROXY'] = {
        'ENABLED': 'True',
        'PROXY_LIST': 'http://proxy1.example.com:8080\nhttp://proxy2.example.com:8080',
        'ROTATION_STRATEGY': 'round_robin',
        'HEALTH_CHECK': 'True'
    }

    with open(temp_config_file, 'w') as f:
        config.write(f)

    return temp_config_file


@pytest.fixture
def mock_driver():
    """Create a mock Selenium WebDriver."""
    driver = MagicMock()
    driver.get_cookie.return_value = {'value': 'test_session_cookie'}
    driver.current_url = 'https://ais.usvisa-info.com/en-ca/niv/users/sign_in'
    return driver


@pytest.fixture
def mock_successful_dates_response():
    """Mock successful API response with dates."""
    return '[{"date": "2027-07-15"}, {"date": "2027-07-16"}, {"date": "2027-07-19"}]'


@pytest.fixture
def mock_empty_response():
    """Mock empty API response (potential ban indicator)."""
    return '[]'


@pytest.fixture
def mock_api_response():
    """Factory fixture for creating mock API responses."""
    def _create_response(status_code=200, body='[]', headers=None):
        response = Mock()
        response.status_code = status_code
        response.text = body
        response.headers = headers or {}

        if status_code == 200:
            import json
            try:
                response.json.return_value = json.loads(body)
            except json.JSONDecodeError:
                response.json.side_effect = json.JSONDecodeError("Invalid JSON", body, 0)
        else:
            response.json.side_effect = Exception(f"HTTP {status_code}")

        return response

    return _create_response


@pytest.fixture
def mock_cloudflare_403_response(mock_api_response):
    """Mock Cloudflare 403 ban response."""
    return mock_api_response(
        status_code=403,
        body='<html><body>Access Denied</body></html>',
        headers={'cf-ray': '1234567890abcdef-YYZ'}
    )


@pytest.fixture
def mock_429_with_retry_after(mock_api_response):
    """Mock 429 rate limit response with Retry-After header."""
    return mock_api_response(
        status_code=429,
        body='Rate limited',
        headers={'Retry-After': '300'}
    )


@pytest.fixture
def sample_proxy_list():
    """Sample list of proxies for testing."""
    return [
        'http://user1:pass1@proxy1.example.com:8080',
        'http://user2:pass2@proxy2.example.com:8080',
        'http://user3:pass3@proxy3.example.com:8080',
    ]


@pytest.fixture
def temp_log_dir():
    """Create a temporary log directory."""
    import tempfile
    log_dir = tempfile.mkdtemp()
    yield log_dir

    # Cleanup
    import shutil
    if os.path.exists(log_dir):
        shutil.rmtree(log_dir)


# Markers for test categorization
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
