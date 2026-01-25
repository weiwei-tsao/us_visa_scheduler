
import os
import re
from datetime import datetime

def analyze_pm2_logs(log_path):
    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}")
        return

    print(f"Analyzing {log_path}...\n")

    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    sessions = []
    current_session = None

    # Regex patterns
    # Line format: YYYY-MM-DD HH:MM:SS: message
    timestamp_pat = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}):')
    
    # Events
    # Detecting "login successful!" which indicates a fresh start or re-login
    # We want to distinguish fresh starts if possible.
    # Usually a fresh start is followed by "Request count: 1".
    # But re-login might not reset request count? 
    # Let's count "login successful!" as a "Login Event".
    
    login_pat = re.compile(r'login successful!')
    relogin_pat = re.compile(r'\[SESSION\] Re-login successful!')
    request_pat = re.compile(r'Request count: (\d+)')
    sleep_pat = re.compile(r'Sleep for ([\d\.]+) hours')
    working_time_pat = re.compile(r'Working Time:\s+~\s+([\d\.]+)\s+minutes')

    events = []

    for line in lines:
        match = timestamp_pat.match(line)
        if not match:
            continue
        
        ts_str = match.group(1)
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
            
        content = line[len(match.group(0)):].strip()

        if login_pat.search(content) and not relogin_pat.search(content):
            events.append({'type': 'LOGIN', 'ts': ts})
        elif relogin_pat.search(content):
            events.append({'type': 'RELOGIN', 'ts': ts})
        elif "Probabely banned" in content:
            events.append({'type': 'BAN', 'ts': ts})
        else:
            m_req = request_pat.search(content)
            if m_req:
                count = int(m_req.group(1))
                events.append({'type': 'REQUEST', 'ts': ts, 'count': count})
            
            m_sleep = sleep_pat.search(content)
            if m_sleep:
                hours = float(m_sleep.group(1))
                events.append({'type': 'SLEEP', 'ts': ts, 'hours': hours})

    # Now process events into sessions
    # A session is generally: LOGIN -> [REQUESTS/RELOGINS] -> [SLEEP/END]
    
    grouped_sessions = []
    current = None
    
    for e in events:
        if e['type'] == 'LOGIN':
            # If we see a login, it generally starts a new session context unless it's a re-login (which we filtered out mostly, but let's see)
            # Actually, if we have a current session and we see 'LOGIN' again, it implies the script restarted or re-authenticated.
            
            # Check if this is a "Start" of a sequence. 
            # If the previous event was close in time (milliseconds), maybe it's duplicate? No, logs are line by line.
            
            if current:
                grouped_sessions.append(current)
            
            current = {
                'start_time': e['ts'],
                'end_time': e['ts'],
                'requests': 0,
                'relogins': 0,
                'outcome': 'Unknown (Running or Terminated)',
                'last_req_count': 0
            }
        
        elif e['type'] == 'RELOGIN':
            if current:
                current['relogins'] += 1
                current['end_time'] = e['ts']
        
        elif e['type'] == 'REQUEST':
            if not current:
                # Request without login? Maybe log started in middle of run
                current = {
                    'start_time': e['ts'],
                    'end_time': e['ts'],
                    'requests': 0,
                    'relogins': 0,
                    'outcome': 'Continued from previous log',
                    'last_req_count': 0
                }
            current['requests'] += 1
            current['last_req_count'] = e['count']
            current['end_time'] = e['ts']
            
        elif e['type'] == 'BAN':
            if current:
                current['outcome'] = 'Soft Ban Detected'
                current['end_time'] = e['ts']
                
        elif e['type'] == 'SLEEP':
            if current:
                current['outcome'] = f"Sleeping for {e['hours']}h"
                current['end_time'] = e['ts']

    if current:
        grouped_sessions.append(current)

    # Print Report
    print(f"{'Start Time':<20} | {'End Time':<20} | {'Duration':<10} | {'Reqs':<5} | {'Relogins':<8} | {'Outcome'}")
    print("-" * 100)
    
    for s in grouped_sessions:
        duration = s['end_time'] - s['start_time']
        dur_str = str(duration).split('.')[0] # Remove microseconds
        print(f"{str(s['start_time']):<20} | {str(s['end_time']):<20} | {dur_str:<10} | {s['requests']:<5} | {s['relogins']:<8} | {s['outcome']}")

    print("-" * 100)
    print(f"Total Sessions Detected: {len(grouped_sessions)}")

if __name__ == "__main__":
    analyze_pm2_logs(os.path.join(os.path.dirname(__file__), 'logs', 'pm2-out.log'))
