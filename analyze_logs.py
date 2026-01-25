
import os
import re
from datetime import datetime
from collections import defaultdict

def parse_logs(log_dir):
    available_dates = set()
    
    # Iterate over all files in the logs directory
    if not os.path.exists(log_dir):
        print(f"Directory not found: {log_dir}")
        return

    files = [f for f in os.listdir(log_dir) if f.startswith('log_') and f.endswith('.txt')]
    
    print(f"Found {len(files)} log files.")

    for filename in files:
        filepath = os.path.join(log_dir, filename)
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        collecting = False
        for line in lines:
            line = line.strip()
            
            if "Available dates:" in line:
                collecting = True
                continue
            
            if collecting:
                # Stop if we hit a timestamp line or separator or empty line that signifies end of block
                # Timestamps look like "00:37:57.326189:" or "2026-01-24..."
                # But easiest check is if the line DOES NOT contain a date or matches strictly other patterns.
                # However, simpler approach: just find all YYYY-MM-DD in the line.
                # If no dates found and line is not empty, probably end of section.
                
                # Check for timestamp pattern roughly (e.g. HH:MM:SS) at start
                if re.match(r'^\d{2}:\d{2}:\d{2}', line) or line.startswith('---') or line.startswith('==='):
                    collecting = False
                    continue
                
                # Regex to find dates
                dates_in_line = re.findall(r'\d{4}-\d{2}-\d{2}', line)
                
                if not dates_in_line:
                    # If we are collecting but find no dates, maybe we are done
                    # But be careful of empty lines between "Available dates:" and dates? 
                    # The logs showed dates immediately.
                    if line: # if line has text but no dates, stop
                        collecting = False
                else:
                    for d in dates_in_line:
                        # Exclude session start/log timestamps if they accidentally match (unlikely with this logic, but good to be safe)
                        # The dates we want are typically future dates.
                        available_dates.add(d)

    return available_dates

def analyze_dates(dates):
    if not dates:
        print("No available dates found in logs.")
        return

    sorted_dates = sorted(list(dates))
    total_dates = len(sorted_dates)
    
    print("\n" + "="*50)
    print(" ANALYSIS OF AVAILABLE DATES")
    print("="*50)
    print(f"Total Unique Available Dates Found: {total_dates}")
    print(f"Earliest Date: {sorted_dates[0]}")
    print(f"Latest Date:   {sorted_dates[-1]}")
    print("-" * 50)
    
    # Group by Year-Month
    by_month = defaultdict(int)
    for date_str in sorted_dates:
        # date_str is YYYY-MM-DD
        year_month = date_str[:7] # YYYY-MM
        by_month[year_month] += 1
        
    print("\nAvailability by Month:")
    sorted_months = sorted(by_month.keys())
    for month in sorted_months:
        print(f"  {month}: {by_month[month]} dates detected")
        
    print("-" * 50)
    print("\nDetailed List of Available Dates:")

    # Print in a grid format (4 columns to fit within ~50 char width)
    num_cols = 4
    col_width = 12  # "YYYY-MM-DD" is 10 chars + 2 padding

    for i in range(0, len(sorted_dates), num_cols):
        row = sorted_dates[i:i+num_cols]
        print("".join(date.ljust(col_width) for date in row))

    print("\n" + "="*50)

if __name__ == "__main__":
    log_directory = os.path.join(os.path.dirname(__file__), 'logs')
    print(f"Scanning directory: {log_directory}...")
    dates = parse_logs(log_directory)
    analyze_dates(dates)
