"""
Mock API responses for testing US Visa Scheduler.

This module provides realistic mock responses that simulate
various states of the usvisa-info.com API.
"""

import json
from datetime import datetime, timedelta


class MockResponses:
    """Collection of mock API responses."""

    @staticmethod
    def dates_available(dates=None):
        """
        Mock response with available appointment dates.

        Args:
            dates: List of date strings (YYYY-MM-DD format).
                   If None, generates dates starting from 6 months out.
        """
        if dates is None:
            # Generate realistic dates (6+ months out)
            start = datetime.now() + timedelta(days=180)
            dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d")
                     for i in range(0, 30, 2)]

        return {
            'status_code': 200,
            'body': json.dumps([{"date": d, "business_day": True} for d in dates]),
            'headers': {
                'Content-Type': 'application/json',
                'X-Request-Id': 'mock-request-123'
            }
        }

    @staticmethod
    def dates_empty():
        """
        Mock empty response - could indicate rate limiting or no availability.

        This is the ambiguous response that needs better detection.
        """
        return {
            'status_code': 200,
            'body': '[]',
            'headers': {
                'Content-Type': 'application/json',
                'X-Request-Id': 'mock-request-456'
            }
        }

    @staticmethod
    def times_available(date, times=None):
        """
        Mock response with available time slots for a date.

        Args:
            date: The date string (YYYY-MM-DD)
            times: List of time strings. If None, provides default times.
        """
        if times is None:
            times = ["09:00", "09:30", "10:00", "10:30", "11:00",
                     "14:00", "14:30", "15:00", "15:30"]

        return {
            'status_code': 200,
            'body': json.dumps({
                "available_times": times,
                "business_day": True
            }),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    @staticmethod
    def cloudflare_403_ban():
        """
        Mock Cloudflare 403 forbidden response.

        This is a definite ban indicator.
        """
        return {
            'status_code': 403,
            'body': '''
            <!DOCTYPE html>
            <html>
            <head><title>Access denied</title></head>
            <body>
                <h1>Sorry, you have been blocked</h1>
                <p>You are unable to access ais.usvisa-info.com</p>
                <p>Ray ID: 1234567890abcdef-YYZ</p>
            </body>
            </html>
            ''',
            'headers': {
                'Content-Type': 'text/html',
                'cf-ray': '1234567890abcdef-YYZ',
                'cf-cache-status': 'DYNAMIC'
            }
        }

    @staticmethod
    def cloudflare_429_rate_limit(retry_after=300):
        """
        Mock Cloudflare 429 rate limit response.

        Args:
            retry_after: Seconds to wait before retrying.
        """
        return {
            'status_code': 429,
            'body': '''
            <!DOCTYPE html>
            <html>
            <head><title>Too Many Requests</title></head>
            <body>
                <h1>Error 1015</h1>
                <p>You are being rate limited</p>
            </body>
            </html>
            ''',
            'headers': {
                'Content-Type': 'text/html',
                'Retry-After': str(retry_after),
                'cf-ray': '0987654321fedcba-YYZ'
            }
        }

    @staticmethod
    def server_error_503():
        """
        Mock 503 Service Unavailable - maintenance or overload.
        """
        return {
            'status_code': 503,
            'body': '''
            <!DOCTYPE html>
            <html>
            <head><title>Service Unavailable</title></head>
            <body>
                <h1>Service Temporarily Unavailable</h1>
                <p>The server is temporarily unable to service your request.</p>
            </body>
            </html>
            ''',
            'headers': {
                'Content-Type': 'text/html',
                'Retry-After': '60'
            }
        }

    @staticmethod
    def session_expired_401():
        """
        Mock 401 Unauthorized - session expired.
        """
        return {
            'status_code': 401,
            'body': json.dumps({
                'error': 'Unauthorized',
                'message': 'Session expired, please login again'
            }),
            'headers': {
                'Content-Type': 'application/json',
                'WWW-Authenticate': 'Bearer'
            }
        }

    @staticmethod
    def reschedule_success(date, time):
        """
        Mock successful reschedule response.
        """
        return {
            'status_code': 200,
            'body': f'''
            <!DOCTYPE html>
            <html>
            <body>
                <div class="alert alert-success">
                    Successfully Scheduled
                </div>
                <p>Your appointment has been scheduled for {date} at {time}</p>
            </body>
            </html>
            ''',
            'headers': {
                'Content-Type': 'text/html'
            }
        }

    @staticmethod
    def reschedule_failure(reason="Slot no longer available"):
        """
        Mock failed reschedule response.
        """
        return {
            'status_code': 200,
            'body': f'''
            <!DOCTYPE html>
            <html>
            <body>
                <div class="alert alert-danger">
                    {reason}
                </div>
            </body>
            </html>
            ''',
            'headers': {
                'Content-Type': 'text/html'
            }
        }


class MockSiteStatus:
    """Mock responses for external site status checks."""

    @staticmethod
    def site_up():
        """Site is operational."""
        return {
            'status_code': 200,
            'body': json.dumps({
                'status': 'up',
                'response_time': 245,
                'last_checked': datetime.now().isoformat()
            }),
            'headers': {'Content-Type': 'application/json'}
        }

    @staticmethod
    def site_down():
        """Site is down for everyone."""
        return {
            'status_code': 200,
            'body': json.dumps({
                'status': 'down',
                'response_time': None,
                'last_checked': datetime.now().isoformat()
            }),
            'headers': {'Content-Type': 'application/json'}
        }

    @staticmethod
    def site_degraded():
        """Site is experiencing issues."""
        return {
            'status_code': 200,
            'body': json.dumps({
                'status': 'degraded',
                'response_time': 5000,
                'last_checked': datetime.now().isoformat()
            }),
            'headers': {'Content-Type': 'application/json'}
        }


# Helper function to convert mock response to requests.Response-like object
def create_mock_response(mock_data):
    """
    Convert mock data dict to a Mock object that behaves like requests.Response.

    Args:
        mock_data: Dict with 'status_code', 'body', and 'headers' keys.

    Returns:
        Mock object with Response-like interface.
    """
    from unittest.mock import Mock

    response = Mock()
    response.status_code = mock_data['status_code']
    response.text = mock_data['body']
    response.content = mock_data['body'].encode('utf-8')
    response.headers = mock_data['headers']

    # Handle JSON parsing
    try:
        response.json.return_value = json.loads(mock_data['body'])
    except json.JSONDecodeError:
        response.json.side_effect = json.JSONDecodeError(
            "Invalid JSON", mock_data['body'], 0
        )

    return response
