"""
Structured logging module for US Visa Scheduler.

Features:
- Structured JSON logging for machine parsing
- Human-readable console output
- Automatic log rotation by size and date
- Error categorization and context tracking
- Operation tracking with attempt counts
"""

import json
import logging
import os
import re
import sys
import glob
import gzip
import shutil
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from enum import Enum
from typing import Optional, Dict, Any, List


# Patterns for sensitive data that should be redacted
SENSITIVE_PATTERNS = [
    (re.compile(r'_yatri_session["\']?\s*[:=]\s*["\']?[\w\-]+', re.IGNORECASE), '_yatri_session=[REDACTED]'),
    (re.compile(r'password["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', re.IGNORECASE), 'password=[REDACTED]'),
    (re.compile(r'token["\']?\s*[:=]\s*["\']?[\w\-\.]+', re.IGNORECASE), 'token=[REDACTED]'),
    (re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?[\w\-]+', re.IGNORECASE), 'api_key=[REDACTED]'),
    (re.compile(r'session[_-]?id["\']?\s*[:=]\s*["\']?[\w\-]+', re.IGNORECASE), 'session_id=[REDACTED]'),
    (re.compile(r'cookie["\']?\s*[:=]\s*["\']?[^"\'\s]{20,}', re.IGNORECASE), 'cookie=[REDACTED]'),
]


def scrub_sensitive_data(text: str) -> str:
    """Remove sensitive data patterns from text."""
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def scrub_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively scrub sensitive data from dictionary."""
    if not isinstance(data, dict):
        return data

    result = {}
    for key, value in data.items():
        # Check if key itself indicates sensitive data
        key_lower = key.lower()
        if any(s in key_lower for s in ['password', 'token', 'secret', 'cookie', 'session', 'api_key']):
            result[key] = '[REDACTED]'
        elif isinstance(value, str):
            result[key] = scrub_sensitive_data(value)
        elif isinstance(value, dict):
            result[key] = scrub_dict(value)
        elif isinstance(value, list):
            result[key] = [scrub_dict(v) if isinstance(v, dict) else scrub_sensitive_data(v) if isinstance(v, str) else v for v in value]
        else:
            result[key] = value
    return result


class RotatingJsonWriter:
    """
    Simple rotating file writer for JSON logs.

    Rotates when file exceeds max_bytes. Keeps up to backup_count old files.
    Optionally compresses old files.
    """

    def __init__(
        self,
        filepath: str,
        max_bytes: int = 10*1024*1024,  # 10MB default
        backup_count: int = 5,
        compress: bool = True
    ):
        self.filepath = filepath
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.compress = compress
        self._file = None
        self._open()

    def _open(self):
        """Open or reopen the log file."""
        if self._file:
            self._file.close()
        self._file = open(self.filepath, 'a', encoding='utf-8')

    def _should_rotate(self) -> bool:
        """Check if rotation is needed."""
        try:
            return os.path.getsize(self.filepath) >= self.max_bytes
        except OSError:
            return False

    def _rotate(self):
        """Perform log rotation."""
        self._file.close()

        # Remove oldest backup if at limit
        for i in range(self.backup_count - 1, 0, -1):
            src = f"{self.filepath}.{i}" + (".gz" if self.compress else "")
            dst = f"{self.filepath}.{i+1}" + (".gz" if self.compress else "")
            if os.path.exists(src):
                if i + 1 > self.backup_count:
                    os.remove(src)
                else:
                    os.rename(src, dst)

        # Rotate current file to .1
        if os.path.exists(self.filepath):
            rotated = f"{self.filepath}.1"
            os.rename(self.filepath, rotated)

            # Compress if enabled
            if self.compress:
                with open(rotated, 'rb') as f_in:
                    with gzip.open(f"{rotated}.gz", 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(rotated)

        # Reopen fresh file
        self._open()

    def write(self, line: str):
        """Write a line, rotating if needed."""
        if self._should_rotate():
            self._rotate()
        self._file.write(line)

    def flush(self):
        """Flush the file."""
        if self._file:
            self._file.flush()

    def close(self):
        """Close the file."""
        if self._file:
            self._file.close()
            self._file = None


class LogCategory(Enum):
    """Error/event categories for quick filtering."""
    SESSION = "SESSION"       # Login, session expiry, relogin
    BOOKING = "BOOKING"       # Reschedule attempts, success/failure
    NETWORK = "NETWORK"       # HTTP errors, timeouts, connection issues
    PROXY = "PROXY"           # Proxy rotation, health checks
    BAN = "BAN"               # Rate limiting, ban detection
    SELENIUM = "SELENIUM"     # WebDriver errors, element issues
    SYSTEM = "SYSTEM"         # Startup, shutdown, config
    HEARTBEAT = "HEARTBEAT"   # Periodic status updates


class OperationType(Enum):
    """Types of operations being performed."""
    GET_DATES = "get_dates"
    GET_TIMES = "get_times"
    RESCHEDULE = "reschedule"
    LOGIN = "login"
    RELOGIN = "relogin"
    PROXY_ROTATE = "proxy_rotate"
    NOTIFICATION = "notification"


class StructuredLogger:
    """
    Structured logger with context tracking and multiple outputs.

    Outputs:
    - Console: Human-readable format
    - JSON file: Machine-parseable structured logs
    - Daily file: Traditional text logs (backward compatible)
    """

    def __init__(self, log_dir: str = "logs", app_name: str = "visa_scheduler"):
        self.log_dir = log_dir
        self.app_name = app_name
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Current operation context
        self._current_operation: Optional[str] = None
        self._attempt_count: int = 0
        self._request_count: int = 0

        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)

        # Setup loggers
        self._setup_loggers()

    def _setup_loggers(self):
        """Configure all log handlers."""
        # Main logger for human-readable output
        self.logger = logging.getLogger(self.app_name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []  # Clear existing handlers

        # Console handler - human readable
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # Error-only file - for quick error review
        error_path = os.path.join(self.log_dir, f"{self.app_name}.error.log")
        error_handler = RotatingFileHandler(
            error_path,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(error_formatter)
        self.logger.addHandler(error_handler)

        # JSON file - with rotation (10MB max, 5 backups, compressed)
        json_path = os.path.join(self.log_dir, f"{self.app_name}.json.log")
        self._json_writer = RotatingJsonWriter(
            json_path,
            max_bytes=10*1024*1024,  # 10MB
            backup_count=5,
            compress=True
        )

    def _build_log_entry(
        self,
        level: str,
        category: LogCategory,
        message: str,
        operation: Optional[OperationType] = None,
        attempt: Optional[int] = None,
        max_attempts: Optional[int] = None,
        error_type: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Build structured log entry with sensitive data scrubbed."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "category": category.value,
            "message": scrub_sensitive_data(message),
            "session_id": self.session_id,
            "request_count": self._request_count,
        }

        if operation:
            entry["operation"] = operation.value
        if attempt is not None:
            entry["attempt"] = attempt
        if max_attempts is not None:
            entry["max_attempts"] = max_attempts
        if error_type:
            entry["error_type"] = error_type
        if extra:
            entry["extra"] = scrub_dict(extra)

        return entry

    def _log(
        self,
        level: int,
        category: LogCategory,
        message: str,
        operation: Optional[OperationType] = None,
        attempt: Optional[int] = None,
        max_attempts: Optional[int] = None,
        error_type: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ):
        """Internal logging method."""
        level_name = logging.getLevelName(level)

        # Build structured entry for JSON log
        entry = self._build_log_entry(
            level_name, category, message,
            operation, attempt, max_attempts, error_type, extra
        )

        # Build human-readable message for console
        parts = [f"[{category.value}]"]
        if operation:
            parts.append(f"[{operation.value}]")
        if attempt is not None and max_attempts is not None:
            parts.append(f"[{attempt}/{max_attempts}]")
        parts.append(message)
        if error_type:
            parts.append(f"(type: {error_type})")

        human_message = " ".join(parts)

        # Write JSON to rotating JSON file
        json_line = json.dumps(entry, ensure_ascii=False)
        self._json_writer.write(json_line + '\n')
        self._json_writer.flush()

        # Log human-readable to console and error file
        self.logger.log(level, human_message)

    # ==================== Public API ====================

    def set_request_count(self, count: int):
        """Update current request count."""
        self._request_count = count

    def increment_request_count(self) -> int:
        """Increment and return request count."""
        self._request_count += 1
        return self._request_count

    # --- Session events ---

    def session_start(self):
        """Log new session start."""
        self._log(
            logging.INFO, LogCategory.SESSION,
            f"New session started (ID: {self.session_id})"
        )

    def session_expired(self, reason: str = ""):
        """Log session expiration."""
        self._log(
            logging.WARNING, LogCategory.SESSION,
            f"Session expired: {reason}" if reason else "Session expired",
            error_type="SessionExpired"
        )

    def login_success(self):
        """Log successful login."""
        self._log(logging.INFO, LogCategory.SESSION, "Login successful")

    def login_failed(self, error: Exception, attempt: int = 1, max_attempts: int = 3):
        """Log failed login attempt."""
        self._log(
            logging.ERROR, LogCategory.SESSION,
            f"Login failed: {str(error)}",
            operation=OperationType.LOGIN,
            attempt=attempt,
            max_attempts=max_attempts,
            error_type=type(error).__name__
        )

    def relogin_attempt(self, attempt: int, max_attempts: int):
        """Log relogin attempt."""
        self._log(
            logging.INFO, LogCategory.SESSION,
            "Attempting session recovery (relogin)",
            operation=OperationType.RELOGIN,
            attempt=attempt,
            max_attempts=max_attempts
        )

    # --- Booking events ---

    def dates_found(self, dates: list, earliest: str):
        """Log available dates found."""
        self._log(
            logging.INFO, LogCategory.BOOKING,
            f"Found {len(dates)} available dates, earliest: {earliest}",
            operation=OperationType.GET_DATES,
            extra={"date_count": len(dates), "earliest": earliest}
        )

    def dates_empty(self):
        """Log empty dates response (potential ban)."""
        self._log(
            logging.WARNING, LogCategory.BAN,
            "Empty dates response - possible rate limiting",
            operation=OperationType.GET_DATES
        )

    def reschedule_start(self, date: str):
        """Log reschedule attempt start."""
        self._log(
            logging.INFO, LogCategory.BOOKING,
            f"Starting reschedule for {date}",
            operation=OperationType.RESCHEDULE,
            extra={"target_date": date}
        )

    def reschedule_attempt(self, date: str, attempt: int, max_attempts: int):
        """Log reschedule retry attempt."""
        self._log(
            logging.INFO, LogCategory.BOOKING,
            f"Reschedule attempt for {date}",
            operation=OperationType.RESCHEDULE,
            attempt=attempt,
            max_attempts=max_attempts,
            extra={"target_date": date}
        )

    def reschedule_success(self, date: str, time: str):
        """Log successful reschedule."""
        self._log(
            logging.INFO, LogCategory.BOOKING,
            f"Successfully rescheduled to {date} {time}",
            operation=OperationType.RESCHEDULE,
            extra={"booked_date": date, "booked_time": time}
        )

    def reschedule_failed(self, date: str, reason: str, attempt: int = 1, max_attempts: int = 3):
        """Log failed reschedule."""
        self._log(
            logging.ERROR, LogCategory.BOOKING,
            f"Reschedule failed for {date}: {reason}",
            operation=OperationType.RESCHEDULE,
            attempt=attempt,
            max_attempts=max_attempts,
            extra={"target_date": date, "reason": reason}
        )

    def reschedule_exception(self, date: str, error: Exception, attempt: int, max_attempts: int):
        """Log reschedule exception (ChromeDriver crash etc.)."""
        self._log(
            logging.ERROR, LogCategory.SELENIUM,
            f"Reschedule exception for {date}: {str(error)[:200]}",
            operation=OperationType.RESCHEDULE,
            attempt=attempt,
            max_attempts=max_attempts,
            error_type=type(error).__name__,
            extra={"target_date": date}
        )

    def slot_taken(self, date: str):
        """Log slot was taken (race condition)."""
        self._log(
            logging.WARNING, LogCategory.BOOKING,
            f"Slot taken before booking: {date}",
            operation=OperationType.RESCHEDULE,
            extra={"target_date": date}
        )

    # --- Network events ---

    def network_error(self, operation: str, error: Exception, attempt: int = 1, max_attempts: int = 3):
        """Log network error."""
        self._log(
            logging.ERROR, LogCategory.NETWORK,
            f"Network error during {operation}: {str(error)}",
            attempt=attempt,
            max_attempts=max_attempts,
            error_type=type(error).__name__
        )

    def request_timeout(self, operation: str, timeout_seconds: int):
        """Log request timeout."""
        self._log(
            logging.WARNING, LogCategory.NETWORK,
            f"Request timeout ({timeout_seconds}s) during {operation}",
            error_type="Timeout",
            extra={"timeout_seconds": timeout_seconds}
        )

    # --- Proxy events ---

    def proxy_loaded(self, count: int, strategy: str):
        """Log proxy configuration loaded."""
        self._log(
            logging.INFO, LogCategory.PROXY,
            f"Loaded {count} proxies (strategy: {strategy})",
            extra={"proxy_count": count, "strategy": strategy}
        )

    def proxy_rotate(self, from_proxy: str, to_proxy: str, reason: str = ""):
        """Log proxy rotation."""
        self._log(
            logging.INFO, LogCategory.PROXY,
            f"Rotated proxy: {from_proxy} -> {to_proxy}" + (f" ({reason})" if reason else ""),
            operation=OperationType.PROXY_ROTATE,
            extra={"from": from_proxy, "to": to_proxy, "reason": reason}
        )

    def proxy_exhausted(self):
        """Log all proxies exhausted."""
        self._log(
            logging.ERROR, LogCategory.PROXY,
            "All proxies exhausted",
            operation=OperationType.PROXY_ROTATE
        )

    # --- Ban detection ---

    def ban_detected(self, ban_type: str, cooldown_minutes: int, consecutive_count: int):
        """Log ban detection."""
        self._log(
            logging.WARNING, LogCategory.BAN,
            f"Ban detected ({ban_type}), cooling down {cooldown_minutes} minutes",
            extra={
                "ban_type": ban_type,
                "cooldown_minutes": cooldown_minutes,
                "consecutive_empty": consecutive_count
            }
        )

    # --- System events ---

    def system_start(self, config_summary: Dict[str, Any] = None):
        """Log system startup."""
        self._log(
            logging.INFO, LogCategory.SYSTEM,
            "Visa Scheduler started",
            extra=config_summary
        )

    def system_shutdown(self, reason: str, exit_code: int):
        """Log system shutdown."""
        self._log(
            logging.INFO, LogCategory.SYSTEM,
            f"Shutting down: {reason} (exit code: {exit_code})",
            extra={"exit_code": exit_code, "reason": reason}
        )

    def work_limit_reached(self, running_minutes: float):
        """Log work limit reached."""
        self._log(
            logging.INFO, LogCategory.SYSTEM,
            f"Work limit reached after {running_minutes:.1f} minutes",
            extra={"running_minutes": running_minutes}
        )

    # --- Heartbeat ---

    def heartbeat(self, request_count: int, running_minutes: float, extra_stats: Dict[str, Any] = None):
        """Log periodic heartbeat."""
        stats = {
            "request_count": request_count,
            "running_minutes": running_minutes
        }
        if extra_stats:
            stats.update(extra_stats)

        self._log(
            logging.INFO, LogCategory.HEARTBEAT,
            f"Heartbeat: {request_count} requests, running {running_minutes:.0f} min",
            extra=stats
        )

    # --- Generic logging ---

    def info(self, category: LogCategory, message: str, **kwargs):
        """Generic info log."""
        self._log(logging.INFO, category, message, extra=kwargs if kwargs else None)

    def warning(self, category: LogCategory, message: str, **kwargs):
        """Generic warning log."""
        self._log(logging.WARNING, category, message, extra=kwargs if kwargs else None)

    def error(self, category: LogCategory, message: str, error: Exception = None, **kwargs):
        """Generic error log."""
        extra = kwargs if kwargs else {}
        error_type = type(error).__name__ if error else None
        if error:
            extra["error_message"] = str(error)
        self._log(
            logging.ERROR, category, message,
            error_type=error_type,
            extra=extra if extra else None
        )


# Global logger instance
_logger: Optional[StructuredLogger] = None


def get_logger() -> StructuredLogger:
    """Get or create global logger instance."""
    global _logger
    if _logger is None:
        _logger = StructuredLogger()
    return _logger


def init_logger(log_dir: str = "logs", app_name: str = "visa_scheduler") -> StructuredLogger:
    """Initialize global logger with custom settings."""
    global _logger
    _logger = StructuredLogger(log_dir=log_dir, app_name=app_name)
    return _logger
