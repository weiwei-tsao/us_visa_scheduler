#!/usr/bin/env python3
"""
Log Analyzer for US Visa Scheduler.

Analyzes structured JSON logs to provide:
- Error summaries by category
- Reschedule attempt statistics
- Ban detection patterns
- Session health overview

Usage:
    python log_analyzer.py                    # Analyze today's logs
    python log_analyzer.py --date 2026-02-02  # Analyze specific date
    python log_analyzer.py --last 24h         # Last 24 hours
    python log_analyzer.py --errors           # Show only errors
    python log_analyzer.py --category BOOKING # Filter by category
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional


class LogAnalyzer:
    """Analyze structured log files."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir

    def load_json_logs(self, filepath: str) -> List[Dict[str, Any]]:
        """Load JSON log entries from file."""
        entries = []
        if not os.path.exists(filepath):
            return entries

        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
        return entries

    def filter_by_time(self, entries: List[Dict], start: datetime, end: datetime) -> List[Dict]:
        """Filter entries by time range."""
        filtered = []
        for entry in entries:
            try:
                ts = datetime.fromisoformat(entry.get('timestamp', ''))
                if start <= ts <= end:
                    filtered.append(entry)
            except (ValueError, TypeError):
                continue
        return filtered

    def filter_by_level(self, entries: List[Dict], levels: List[str]) -> List[Dict]:
        """Filter entries by log level."""
        return [e for e in entries if e.get('level') in levels]

    def filter_by_category(self, entries: List[Dict], categories: List[str]) -> List[Dict]:
        """Filter entries by category."""
        return [e for e in entries if e.get('category') in categories]

    def get_summary(self, entries: List[Dict]) -> Dict[str, Any]:
        """Generate summary statistics."""
        if not entries:
            return {"error": "No log entries found"}

        # Time range
        timestamps = []
        for e in entries:
            try:
                timestamps.append(datetime.fromisoformat(e.get('timestamp', '')))
            except (ValueError, TypeError):
                continue

        time_range = {
            "start": min(timestamps).isoformat() if timestamps else None,
            "end": max(timestamps).isoformat() if timestamps else None,
            "duration_minutes": (max(timestamps) - min(timestamps)).total_seconds() / 60 if len(timestamps) > 1 else 0
        }

        # Counts by level
        level_counts = Counter(e.get('level') for e in entries)

        # Counts by category
        category_counts = Counter(e.get('category') for e in entries)

        # Error types
        error_types = Counter(
            e.get('error_type') for e in entries
            if e.get('error_type')
        )

        # Operations summary
        operations = Counter(e.get('operation') for e in entries if e.get('operation'))

        # Reschedule stats
        reschedule_entries = [e for e in entries if e.get('operation') == 'reschedule']
        reschedule_stats = {
            "total_attempts": len(reschedule_entries),
            "successes": len([e for e in reschedule_entries if 'Successfully' in e.get('message', '')]),
            "failures": len([e for e in reschedule_entries if e.get('level') == 'ERROR']),
            "slots_taken": len([e for e in reschedule_entries if 'taken' in e.get('message', '').lower()])
        }

        # Session stats
        session_entries = [e for e in entries if e.get('category') == 'SESSION']
        session_stats = {
            "logins": len([e for e in session_entries if 'successful' in e.get('message', '').lower()]),
            "expirations": len([e for e in session_entries if 'expired' in e.get('message', '').lower()]),
            "relogin_attempts": len([e for e in session_entries if e.get('operation') == 'relogin'])
        }

        # Ban detections with time pattern analysis
        ban_entries = [e for e in entries if e.get('category') == 'BAN']
        ban_by_hour = Counter()
        for e in ban_entries:
            try:
                ts = datetime.fromisoformat(e.get('timestamp', ''))
                ban_by_hour[ts.hour] += 1
            except (ValueError, TypeError):
                pass

        ban_stats = {
            "total_detections": len(ban_entries),
            "empty_responses": len([e for e in ban_entries if 'empty' in e.get('message', '').lower()]),
            "by_hour": dict(sorted(ban_by_hour.items())),  # Hour -> count
            "peak_hours": [h for h, c in ban_by_hour.most_common(3)] if ban_by_hour else []
        }

        return {
            "time_range": time_range,
            "total_entries": len(entries),
            "by_level": dict(level_counts),
            "by_category": dict(category_counts),
            "error_types": dict(error_types),
            "operations": dict(operations),
            "reschedule": reschedule_stats,
            "session": session_stats,
            "ban": ban_stats
        }

    def get_errors(self, entries: List[Dict], limit: int = 50) -> List[Dict]:
        """Get recent errors with context."""
        errors = self.filter_by_level(entries, ['ERROR', 'CRITICAL'])
        # Sort by timestamp descending
        errors.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return errors[:limit]

    def get_reschedule_timeline(self, entries: List[Dict]) -> List[Dict]:
        """Get timeline of reschedule attempts."""
        reschedule_entries = [e for e in entries if e.get('operation') == 'reschedule']
        reschedule_entries.sort(key=lambda x: x.get('timestamp', ''))
        return reschedule_entries

    def print_summary(self, summary: Dict[str, Any]):
        """Print formatted summary."""
        print("\n" + "=" * 60)
        print("LOG ANALYSIS SUMMARY")
        print("=" * 60)

        if "error" in summary:
            print(f"\n{summary['error']}")
            return

        # Time range
        tr = summary['time_range']
        print(f"\nTime Range: {tr['start']} to {tr['end']}")
        print(f"Duration: {tr['duration_minutes']:.1f} minutes")
        print(f"Total Entries: {summary['total_entries']}")

        # By level
        print("\n--- By Level ---")
        for level, count in sorted(summary['by_level'].items()):
            print(f"  {level}: {count}")

        # By category
        print("\n--- By Category ---")
        for cat, count in sorted(summary['by_category'].items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")

        # Errors
        if summary['error_types']:
            print("\n--- Error Types ---")
            for err_type, count in sorted(summary['error_types'].items(), key=lambda x: -x[1]):
                print(f"  {err_type}: {count}")

        # Reschedule stats
        rs = summary['reschedule']
        if rs['total_attempts'] > 0:
            print("\n--- Reschedule Stats ---")
            print(f"  Attempts: {rs['total_attempts']}")
            print(f"  Successes: {rs['successes']}")
            print(f"  Failures: {rs['failures']}")
            print(f"  Slots Taken: {rs['slots_taken']}")

        # Session stats
        ss = summary['session']
        print("\n--- Session Stats ---")
        print(f"  Successful Logins: {ss['logins']}")
        print(f"  Session Expirations: {ss['expirations']}")
        print(f"  Relogin Attempts: {ss['relogin_attempts']}")

        # Ban stats
        bs = summary['ban']
        if bs['total_detections'] > 0:
            print("\n--- Ban Detection ---")
            print(f"  Total Detections: {bs['total_detections']}")
            print(f"  Empty Responses: {bs['empty_responses']}")

        print("\n" + "=" * 60)

    def print_errors(self, errors: List[Dict]):
        """Print error entries."""
        print("\n" + "=" * 60)
        print(f"RECENT ERRORS ({len(errors)} entries)")
        print("=" * 60)

        for e in errors:
            ts = e.get('timestamp', 'N/A')[:19]  # Trim microseconds
            cat = e.get('category', 'N/A')
            msg = e.get('message', 'N/A')
            err_type = e.get('error_type', '')
            attempt = e.get('attempt', '')
            max_att = e.get('max_attempts', '')

            print(f"\n[{ts}] [{cat}]")
            if attempt and max_att:
                print(f"  Attempt: {attempt}/{max_att}")
            if err_type:
                print(f"  Type: {err_type}")
            print(f"  {msg}")

    def print_reschedule_timeline(self, timeline: List[Dict]):
        """Print reschedule timeline."""
        print("\n" + "=" * 60)
        print(f"RESCHEDULE TIMELINE ({len(timeline)} events)")
        print("=" * 60)

        for e in timeline:
            ts = e.get('timestamp', 'N/A')[:19]
            level = e.get('level', 'N/A')
            msg = e.get('message', 'N/A')
            attempt = e.get('attempt', '')
            max_att = e.get('max_attempts', '')

            marker = "✓" if level == "INFO" and "Success" in msg else "✗" if level == "ERROR" else "○"
            attempt_str = f"[{attempt}/{max_att}]" if attempt else ""

            print(f"{marker} [{ts}] {attempt_str} {msg}")


def main():
    parser = argparse.ArgumentParser(description='Analyze visa scheduler logs')
    parser.add_argument('--log-dir', default='logs', help='Log directory')
    parser.add_argument('--date', help='Analyze specific date (YYYY-MM-DD)')
    parser.add_argument('--last', help='Analyze last N hours (e.g., 24h)')
    parser.add_argument('--errors', action='store_true', help='Show only errors')
    parser.add_argument('--category', help='Filter by category')
    parser.add_argument('--reschedule', action='store_true', help='Show reschedule timeline')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    analyzer = LogAnalyzer(args.log_dir)

    # Determine log file to analyze
    json_log_path = os.path.join(args.log_dir, 'visa_scheduler.json.log')

    if not os.path.exists(json_log_path):
        print(f"Log file not found: {json_log_path}")
        print("Note: This analyzer works with the new structured JSON logs.")
        print("Make sure the logger module is integrated into visa.py")
        sys.exit(1)

    # Load entries
    entries = analyzer.load_json_logs(json_log_path)

    if not entries:
        print("No log entries found")
        sys.exit(0)

    # Apply time filter
    if args.last:
        hours = int(args.last.replace('h', ''))
        end = datetime.now()
        start = end - timedelta(hours=hours)
        entries = analyzer.filter_by_time(entries, start, end)
    elif args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d')
        start = target_date
        end = target_date + timedelta(days=1)
        entries = analyzer.filter_by_time(entries, start, end)

    # Apply category filter
    if args.category:
        entries = analyzer.filter_by_category(entries, [args.category.upper()])

    # Output
    if args.errors:
        errors = analyzer.get_errors(entries)
        if args.json:
            print(json.dumps(errors, indent=2))
        else:
            analyzer.print_errors(errors)
    elif args.reschedule:
        timeline = analyzer.get_reschedule_timeline(entries)
        if args.json:
            print(json.dumps(timeline, indent=2))
        else:
            analyzer.print_reschedule_timeline(timeline)
    else:
        summary = analyzer.get_summary(entries)
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            analyzer.print_summary(summary)


if __name__ == '__main__':
    main()
