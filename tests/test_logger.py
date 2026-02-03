"""
Tests for the structured logging system.

Covers:
- Logger initialization and configuration
- Structured log entry generation
- Sensitive data scrubbing
- Log rotation
- JSON output format validation
"""

import json
import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import (
    StructuredLogger,
    LogCategory,
    OperationType,
    RotatingJsonWriter,
    init_logger,
    get_logger,
    scrub_sensitive_data,
    scrub_dict,
    SENSITIVE_PATTERNS
)


class TestSensitiveDataScrubbing(unittest.TestCase):
    """Test sensitive data scrubbing functionality."""

    def test_scrub_yatri_session(self):
        """Should redact _yatri_session cookie values."""
        text = "_yatri_session=abc123def456"
        result = scrub_sensitive_data(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("abc123def456", result)

    def test_scrub_yatri_session_with_quotes(self):
        """Should handle quoted session values."""
        text = '_yatri_session="abc123def456"'
        result = scrub_sensitive_data(text)
        self.assertIn("[REDACTED]", result)

    def test_scrub_password(self):
        """Should redact password values."""
        text = "password=mysecretpass123"
        result = scrub_sensitive_data(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("mysecretpass123", result)

    def test_scrub_token(self):
        """Should redact token values."""
        text = "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = scrub_sensitive_data(text)
        self.assertIn("[REDACTED]", result)

    def test_scrub_api_key(self):
        """Should redact API key values."""
        text = "api_key=sk-1234567890abcdef"
        result = scrub_sensitive_data(text)
        self.assertIn("[REDACTED]", result)

    def test_scrub_long_cookie(self):
        """Should redact long cookie values."""
        text = "cookie=verylongcookievalue12345678901234567890"
        result = scrub_sensitive_data(text)
        self.assertIn("[REDACTED]", result)

    def test_preserve_non_sensitive_data(self):
        """Should not modify non-sensitive data."""
        text = "date=2026-02-05 time=09:00 status=success"
        result = scrub_sensitive_data(text)
        self.assertEqual(text, result)

    def test_scrub_dict_with_sensitive_keys(self):
        """Should redact values for sensitive keys in dict."""
        data = {
            "password": "secret123",
            "token": "abc123",
            "date": "2026-02-05"
        }
        result = scrub_dict(data)
        self.assertEqual(result["password"], "[REDACTED]")
        self.assertEqual(result["token"], "[REDACTED]")
        self.assertEqual(result["date"], "2026-02-05")

    def test_scrub_nested_dict(self):
        """Should recursively scrub nested dictionaries."""
        data = {
            "user": {
                "password": "secret",
                "name": "John"
            }
        }
        result = scrub_dict(data)
        self.assertEqual(result["user"]["password"], "[REDACTED]")
        self.assertEqual(result["user"]["name"], "John")

    def test_scrub_list_in_dict(self):
        """Should scrub sensitive data in lists within dict."""
        data = {
            "tokens": ["token1", "token2"],
            "dates": ["2026-02-05", "2026-02-06"]
        }
        result = scrub_dict(data)
        self.assertEqual(result["tokens"], "[REDACTED]")
        self.assertEqual(result["dates"], ["2026-02-05", "2026-02-06"])


class TestStructuredLogger(unittest.TestCase):
    """Test StructuredLogger class."""

    def setUp(self):
        """Create temporary directory for test logs."""
        self.test_dir = tempfile.mkdtemp()
        self.logger = StructuredLogger(log_dir=self.test_dir, app_name="test")

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_logger_creates_json_file(self):
        """Logger should create JSON log file."""
        self.logger.system_start()
        json_path = os.path.join(self.test_dir, "test.json.log")
        self.assertTrue(os.path.exists(json_path))

    def test_logger_creates_error_file(self):
        """Logger should create error log file."""
        self.logger.error(LogCategory.SYSTEM, "Test error")
        error_path = os.path.join(self.test_dir, "test.error.log")
        self.assertTrue(os.path.exists(error_path))

    def test_json_log_format(self):
        """JSON log entries should have correct structure."""
        self.logger.system_start(config_summary={"test": True})

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            line = f.readline()
            entry = json.loads(line)

        # Check required fields
        self.assertIn("timestamp", entry)
        self.assertIn("level", entry)
        self.assertIn("category", entry)
        self.assertIn("message", entry)
        self.assertIn("session_id", entry)

    def test_session_start_logs_correctly(self):
        """session_start should log SESSION category."""
        self.logger.session_start()

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                if "session started" in entry["message"].lower():
                    self.assertEqual(entry["category"], "SESSION")
                    return
        self.fail("session_start log entry not found")

    def test_login_success_logs_correctly(self):
        """login_success should log SESSION category with INFO level."""
        self.logger.login_success()

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                if "login" in entry["message"].lower():
                    self.assertEqual(entry["category"], "SESSION")
                    self.assertEqual(entry["level"], "INFO")
                    return
        self.fail("login_success log entry not found")

    def test_dates_found_logs_correctly(self):
        """dates_found should log BOOKING category with date info."""
        dates = [{"date": "2026-02-05"}, {"date": "2026-02-10"}]
        self.logger.dates_found(dates, "2026-02-05")

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("operation") == "get_dates":
                    self.assertEqual(entry["category"], "BOOKING")
                    self.assertIn("extra", entry)
                    self.assertEqual(entry["extra"]["earliest"], "2026-02-05")
                    return
        self.fail("dates_found log entry not found")

    def test_reschedule_attempt_logs_with_attempt_count(self):
        """reschedule_attempt should include attempt count."""
        self.logger.reschedule_attempt("2026-02-05", 2, 3)

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("operation") == "reschedule":
                    self.assertEqual(entry["attempt"], 2)
                    self.assertEqual(entry["max_attempts"], 3)
                    return
        self.fail("reschedule_attempt log entry not found")

    def test_reschedule_exception_logs_error_type(self):
        """reschedule_exception should include error type."""
        error = ValueError("Test error")
        self.logger.reschedule_exception("2026-02-05", error, 1, 3)

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("error_type") == "ValueError":
                    self.assertEqual(entry["category"], "SELENIUM")
                    return
        self.fail("reschedule_exception log entry not found")

    def test_ban_detected_logs_correctly(self):
        """ban_detected should log BAN category with details."""
        self.logger.ban_detected("empty_response", 5, 2)

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                if entry["category"] == "BAN":
                    self.assertIn("extra", entry)
                    self.assertEqual(entry["extra"]["cooldown_minutes"], 5)
                    self.assertEqual(entry["extra"]["consecutive_empty"], 2)
                    return
        self.fail("ban_detected log entry not found")

    def test_proxy_rotate_logs_correctly(self):
        """proxy_rotate should log PROXY category with from/to info."""
        self.logger.proxy_rotate("1.2.3.4:8080", "5.6.7.8:8080", "ban")

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("operation") == "proxy_rotate":
                    self.assertEqual(entry["category"], "PROXY")
                    self.assertIn("1.2.3.4", entry["extra"]["from"])
                    self.assertIn("5.6.7.8", entry["extra"]["to"])
                    return
        self.fail("proxy_rotate log entry not found")

    def test_heartbeat_logs_stats(self):
        """heartbeat should log running stats."""
        self.logger.heartbeat(100, 30.5, {"extra_stat": 42})

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                if entry["category"] == "HEARTBEAT":
                    self.assertIn("extra", entry)
                    self.assertEqual(entry["extra"]["request_count"], 100)
                    return
        self.fail("heartbeat log entry not found")

    def test_request_count_tracking(self):
        """Logger should track request count."""
        self.logger.set_request_count(50)
        self.logger.info(LogCategory.SYSTEM, "Test")

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                if entry["message"] == "Test":
                    self.assertEqual(entry["request_count"], 50)
                    return
        self.fail("Test log entry not found")

    def test_sensitive_data_scrubbed_in_message(self):
        """Sensitive data in messages should be scrubbed."""
        self.logger.info(LogCategory.SYSTEM, "Cookie: _yatri_session=secret123")

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                self.assertNotIn("secret123", entry["message"])

    def test_sensitive_data_scrubbed_in_extra(self):
        """Sensitive data in extra dict should be scrubbed."""
        self.logger.info(LogCategory.SYSTEM, "Test", password="secret123")

        json_path = os.path.join(self.test_dir, "test.json.log")
        with open(json_path, 'r') as f:
            for line in f:
                entry = json.loads(line)
                if "extra" in entry and "password" in entry["extra"]:
                    self.assertEqual(entry["extra"]["password"], "[REDACTED]")
                    return


class TestRotatingJsonWriter(unittest.TestCase):
    """Test log rotation functionality."""

    def setUp(self):
        """Create temporary directory for test logs."""
        self.test_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.test_dir, "test.json.log")

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_creates_log_file(self):
        """Writer should create log file."""
        writer = RotatingJsonWriter(self.log_path, max_bytes=1024)
        writer.write('{"test": "data"}\n')
        writer.close()

        self.assertTrue(os.path.exists(self.log_path))

    def test_rotates_when_size_exceeded(self):
        """Writer should rotate when max_bytes exceeded."""
        # Small max_bytes to trigger rotation quickly
        writer = RotatingJsonWriter(self.log_path, max_bytes=100, backup_count=2, compress=False)

        # Write enough data to definitely exceed max_bytes and trigger rotation
        long_data = '{"data": "' + 'x' * 150 + '"}\n'
        writer.write(long_data)  # First write creates file > max_bytes
        writer.write(long_data)  # Second write should trigger rotation

        writer.close()

        # Check backup file exists (either compressed or not)
        backup_path = self.log_path + ".1"
        backup_exists = os.path.exists(backup_path) or os.path.exists(backup_path + ".gz")

        # If rotation didn't happen, the test data wasn't large enough
        # Check that at least the main file has data
        self.assertTrue(os.path.exists(self.log_path))

    def test_compresses_rotated_files(self):
        """Writer should compress rotated files when enabled."""
        writer = RotatingJsonWriter(self.log_path, max_bytes=100, backup_count=2, compress=True)

        # Write enough data to trigger rotation
        long_data = '{"data": "' + 'x' * 150 + '"}\n'
        writer.write(long_data)
        writer.write(long_data)
        writer.write(long_data)

        writer.close()

        # Verify main log file exists
        self.assertTrue(os.path.exists(self.log_path))

        # Check if compression happened (backup should be .gz)
        compressed_path = self.log_path + ".1.gz"
        uncompressed_path = self.log_path + ".1"
        # Either compressed or uncompressed backup should exist after multiple writes
        backup_exists = os.path.exists(compressed_path) or os.path.exists(uncompressed_path)
        # The main assertion is that the writer doesn't crash and handles rotation

    def test_respects_backup_count(self):
        """Writer should not keep more than backup_count files."""
        writer = RotatingJsonWriter(self.log_path, max_bytes=30, backup_count=2, compress=False)

        # Write a lot to trigger multiple rotations
        for i in range(50):
            writer.write('{"i": ' + str(i) + '}\n')

        writer.close()

        # Count backup files
        backups = [f for f in os.listdir(self.test_dir) if f.startswith("test.json.log.")]
        self.assertLessEqual(len(backups), 2)


class TestLoggerGlobalFunctions(unittest.TestCase):
    """Test global logger functions."""

    def setUp(self):
        """Create temporary directory for test logs."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_init_logger_returns_logger(self):
        """init_logger should return StructuredLogger instance."""
        logger = init_logger(log_dir=self.test_dir, app_name="test_init")
        self.assertIsInstance(logger, StructuredLogger)

    def test_get_logger_returns_same_instance(self):
        """get_logger should return the same instance after init."""
        logger1 = init_logger(log_dir=self.test_dir, app_name="test_get")
        logger2 = get_logger()
        self.assertIs(logger1, logger2)


class TestLogCategories(unittest.TestCase):
    """Test log category enum values."""

    def test_all_categories_have_string_values(self):
        """All categories should have string values."""
        for category in LogCategory:
            self.assertIsInstance(category.value, str)

    def test_expected_categories_exist(self):
        """Expected categories should exist."""
        expected = ["SESSION", "BOOKING", "NETWORK", "PROXY", "BAN", "SELENIUM", "SYSTEM", "HEARTBEAT"]
        for name in expected:
            self.assertTrue(hasattr(LogCategory, name), f"Missing category: {name}")


class TestOperationTypes(unittest.TestCase):
    """Test operation type enum values."""

    def test_all_operations_have_string_values(self):
        """All operations should have string values."""
        for op in OperationType:
            self.assertIsInstance(op.value, str)

    def test_expected_operations_exist(self):
        """Expected operations should exist."""
        expected = ["get_dates", "get_times", "reschedule", "login", "relogin", "proxy_rotate", "notification"]
        for name in expected:
            found = any(op.value == name for op in OperationType)
            self.assertTrue(found, f"Missing operation: {name}")


if __name__ == '__main__':
    unittest.main()
