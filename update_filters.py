import os
import re
import hashlib
import datetime
import requests
from datetime import timezone, timedelta

FILTER_FILE = 'Yuusei.txt'
ABPVN_URLS = [
    'https://raw.githubusercontent.com/abpvn/abpvn/master/filter/abpvn_ublock.txt',
    'https://raw.githubusercontent.com/abpvn/abpvn/master/filter/abpvn.txt'
]

MARKER_YUUSEI = '! ----------  Yuusei  ----------'
MARKER_ABPVN = '! ----------  AbpVN ----------'
# Regex to find the start of the next section (any line starting with ! ---)
MARKER_NEXT_REGEX = r'^! -{3,}'

def get_current_time():
    tz = timezone(timedelta(hours=7)) # UTC+7 for Vietnam
    return datetime.datetime.now(tz)

def download_rules(urls):
    rules = set()
    for url in urls:
        try:
            print(f"Downloading {url}...")
            r = requests.get(url)
            r.raise_for_status()
            for line in r.text.splitlines():
                line = line.strip()
                # Skip comments, empty lines, and metadata
                if not line or line.startswith('!') or line.startswith('['):
                    continue
                rules.add(line)
        except Exception as e:
            print(f"Error downloading {url}: {e}")
    return rules

def parse_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    header = []
    yuusei_rules = []
    other_sections = [] # Everything after AbpVN section

    mode = 'HEADER'
    abpvn_found = False

    # Simple state machine
    # HEADER -> (MARKER_YUUSEI) -> YUUSEI_SECTION -> (MARKER_ABPVN) -> ABPVN_SECTION (skip) -> (NEXT_MARKER) -> OTHER

    # However, looking at the file, the sections are strictly ordered?
    # Let's iterate and capture based on markers.

    content_map = {
        'HEADER': [],
        'YUUSEI': [],
        'PRE_ABPVN': [], # Space between Yuusei and AbpVN if any
        'POST_ABPVN': [] # Everything after AbpVN section
    }

    current_section = 'HEADER'

    for line in lines:
        stripped = line.strip()

        if stripped == MARKER_YUUSEI:
            current_section = 'YUUSEI'
            content_map['HEADER'].append(line) # Keep marker in header block or start of Yuusei?
            # Let's put the marker as the first item of Yuusei list effectively,
            # or keep it in the output reconstruction explicitly.
            # actually, let's allow the marker to define the transition.
            continue

        if stripped == MARKER_ABPVN:
            current_section = 'ABPVN_SKIP'
            continue

        # Check if we are in ABPVN_SKIP and hit a new marker
        if current_section == 'ABPVN_SKIP':
            if stripped.startswith('! ') and ('---' in stripped or 'element' in stripped.lower() or 'whitelist' in stripped.lower() or 'rule' in stripped.lower()):
                 # Found next section
                 current_section = 'POST_ABPVN'
                 content_map['POST_ABPVN'].append(line)
                 continue
            else:
                # Still in AbpVN section, ignore this line (we will replace it)
                continue

        if current_section == 'HEADER':
            content_map['HEADER'].append(line)
        elif current_section == 'YUUSEI':
            # Check if we hit AbpVN marker is handled above.
            # Check if we hit some OTHER marker before AbpVN?
            # Assuming structure is fixed.
            content_map['YUUSEI'].append(line)
        elif current_section == 'POST_ABPVN':
            content_map['POST_ABPVN'].append(line)

    return content_map

def main():
    if not os.path.exists(FILTER_FILE):
        print(f"File {FILTER_FILE} not found!")
        return

    # 1. Download new AbpVN rules
    new_abpvn_rules = download_rules(ABPVN_URLS)
    print(f"Downloaded {len(new_abpvn_rules)} unique rules from AbpVN.")

    # 2. Read existing file
    with open(FILTER_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.splitlines()

    # 3. Intelligent Parsing
    # We want to reconstruct the file:
    # [HEADER]
    # [MARKER_YUUSEI]
    # [YUUSEI_RULES]
    # [MARKER_ABPVN]
    # [NEW_ABPVN_RULES]
    # [REST_OF_FILE]

    # Locate markers
    try:
        idx_yuusei = -1
        idx_abpvn = -1

        for i, line in enumerate(lines):
            if line.strip() == MARKER_YUUSEI:
                idx_yuusei = i
            elif line.strip() == MARKER_ABPVN:
                idx_abpvn = i

        if idx_yuusei == -1 or idx_abpvn == -1:
            print("Critical markers not found in file. Aborting.")
            # Fallback or exit?
            # If markers missing, maybe append? But user request is specific.
            return

        # Extract Yuusei Rules
        # From idx_yuusei + 1 to idx_abpvn - 1 (roughly)
        yuusei_lines = lines[idx_yuusei+1 : idx_abpvn]
        yuusei_rules = set()
        for l in yuusei_lines:
            s = l.strip()
            if s and not s.startswith('!'):
                yuusei_rules.add(s)

        # 4. Filter AbpVN rules
        # Remove rules that are already in Yuusei section
        final_abpvn_rules = []
        for rule in sorted(new_abpvn_rules):
            if rule not in yuusei_rules:
                final_abpvn_rules.append(rule)

        print(f"AbpVN rules after deduplication against Yuusei: {len(final_abpvn_rules)}")

        # 5. Identify where AbpVN section ends
        # It ends at the next line starting with '!' that looks like a section header
        idx_abpvn_end = len(lines)
        for i in range(idx_abpvn + 1, len(lines)):
            line = lines[i].strip()
            # Heuristic for next section: starts with ! and has --- or is specific known headers
            if line.startswith('!') and ('---' in line or 'White List' in line or 'Element Hide' in line or 'Adult' in line):
                idx_abpvn_end = i
                break

        # 6. Reconstruct

        # Header + Yuusei
        output_lines = lines[:idx_abpvn + 1] # Includes MARKER_ABPVN

        # Add new AbpVN rules
        output_lines.extend(final_abpvn_rules)

        # Add the rest
        output_lines.extend(lines[idx_abpvn_end:])

        # 7. Update Metadata (Version, Date, Checksum, Counts)
        now = get_current_time()
        version = now.strftime('%Y.%m.%d.%H%M')
        date_str = now.strftime('%d-%m-%Y')

        # Join to calculate stats
        full_text = '\n'.join(output_lines)

        # Recalculate stats
        rule_count = 0
        unique_domains = set()
        for line in output_lines:
            s = line.strip()
            if s and not s.startswith('!'):
                rule_count += 1
                # Rough domain extraction
                if s.startswith('||'):
                    parts = s[2:].split('^')[0].split('/')[0]
                    unique_domains.add(parts)
                elif s.startswith('0.0.0.0 '):
                    unique_domains.add(s.split(' ')[1])

        # Write to temp file first to compute checksum
        temp_content = '\n'.join(output_lines)
        # checksum = hashlib.sha256(temp_content.encode('utf-8')).hexdigest()

        # We need to update the header lines in the content
        # Finding header lines index
        final_output = []
        for line in output_lines:
            if line.startswith('! Version:'):
                final_output.append(f'! Version: {version}')
            elif line.startswith('! Last modified:'):
                final_output.append(f'! Last modified: {date_str}')
            elif line.startswith('! Checksum:'):
                final_output.append('! Checksum: __CHECKSUM_PLACEHOLDER__')
            # Optional: Update counts if they exist in header
            elif line.startswith('! Total rules:'):
                 final_output.append(f'! Total rules: {rule_count}')
            elif line.startswith('! Unique domains:'):
                 final_output.append(f'! Unique domains: {len(unique_domains)}')
            else:
                final_output.append(line)

        content_no_checksum = '\n'.join(final_output)
        checksum = hashlib.sha256(content_no_checksum.replace('__CHECKSUM_PLACEHOLDER__', '').encode('utf-8')).hexdigest()

        final_content = content_no_checksum.replace('__CHECKSUM_PLACEHOLDER__', checksum)

        with open(FILTER_FILE, 'w', encoding='utf-8') as f:
            f.write(final_content)

        print("Update complete.")

    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
