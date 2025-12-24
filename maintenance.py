import re
import requests
import tldextract
from googlesearch import search
import concurrent.futures
import time
import sys

# Constants
FILTER_FILE = "Yuusei.txt"
# Randomize UA slightly or use a very standard one
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT = 15
MAX_WORKERS = 10
RETRIES = 2

def get_unique_domains(content):
    """
    Extracts unique domains from the filter file content.
    Returns a set of domains.
    """
    domains = set()
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('!'):
            continue

        # Regex to capture domain-like strings in adblock rules
        # Common patterns: ||domain.com^, domain.com##selector, domain.com$script
        # We look for the part before the first separator that isn't a valid domain character

        # Remove leading markers
        clean_line = re.sub(r'^(?:@@)?\|\|', '', line)

        # Split by typical adblock separators
        # Separators: ^ (separator), $ (options), # (hiding), / (path)
        parts = re.split(r'[\^\$\#\/]', clean_line)
        potential_domain = parts[0]

        # Basic validation
        if '.' in potential_domain and '*' not in potential_domain:
             # Remove port if any
             domain = potential_domain.split(':')[0]
             domain = domain.rstrip('.')

             # Use tldextract to verify it has a valid structure
             ext = tldextract.extract(domain)
             if ext.domain and ext.suffix:
                 full_domain = f"{ext.subdomain}.{ext.domain}.{ext.suffix}".strip('.')
                 domains.add(full_domain)

    return domains

def check_domain_status(domain):
    """
    Checks if a domain is active with retries.
    Returns True if active, False otherwise.
    """
    for attempt in range(RETRIES + 1):
        try:
            url = f"https://{domain}"
            response = requests.head(url, timeout=TIMEOUT, headers={'User-Agent': USER_AGENT}, allow_redirects=True)
            if response.status_code < 400:
                return True
            # If 403/401, it might be protected but alive.
            # If 5xx, server error but domain exists.
            # If 404, domain exists but page not found (maybe just root is 404).
            # We strictly want to know if the domain is completely gone (NXDOMAIN, Connection Refused).
            # But usually for ad sites, if root is 404/403, we count it as alive enough to not auto-replace blindly.
            if response.status_code in [403, 401, 404, 500, 502, 503]:
                return True

        except (requests.ConnectionError, requests.Timeout):
            # Try HTTP
            try:
                url = f"http://{domain}"
                response = requests.head(url, timeout=TIMEOUT, headers={'User-Agent': USER_AGENT}, allow_redirects=True)
                if response.status_code < 400:
                    return True
                if response.status_code in [403, 401, 404, 500, 502, 503]:
                    return True
            except:
                pass

        # Backoff before retry
        if attempt < RETRIES:
            time.sleep(2)

    return False

def find_replacement_domain(dead_domain):
    """
    Searches for a replacement domain using Google Search.
    Returns the new domain string if found, else None.
    """
    ext = tldextract.extract(dead_domain)
    brand = ext.domain
    if not brand:
        return None

    print(f"Searching for replacement for dead domain: {dead_domain} (Brand: {brand})")

    try:
        # Search for the brand name
        # We handle the generator properly
        search_query = f"{brand} official site"
        results = search(search_query, num_results=5, advanced=True)

        for result in results:
            url = result.url
            res_ext = tldextract.extract(url)

            # Heuristic: If the brand name matches exactly
            if res_ext.domain.lower() == brand.lower():
                new_domain = f"{res_ext.subdomain}.{res_ext.domain}.{res_ext.suffix}".strip('.')

                # If it's different from the dead domain
                if new_domain != dead_domain:
                    # Check if the new domain is active
                    if check_domain_status(new_domain):
                         print(f"Found candidate: {new_domain}")
                         return new_domain

        # If no exact match found, maybe the brand changed slightly?
        # For now, stick to safe replacements (exact brand match).

    except Exception as e:
        print(f"Search error for {dead_domain}: {e}")

    return None

def process_domain(domain):
    """
    Worker function to check a domain and find replacement if dead.
    """
    if check_domain_status(domain):
        return None # Alive

    # Domain is dead, try to find replacement
    new_domain = find_replacement_domain(domain)
    if new_domain:
        return (domain, new_domain)

    return None

def main():
    print("Starting domain maintenance...")

    try:
        with open(FILTER_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"File {FILTER_FILE} not found.")
        sys.exit(1)

    domains = get_unique_domains(content)
    print(f"Found {len(domains)} unique domains to check.")

    replacements = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_domain = {executor.submit(process_domain, domain): domain for domain in domains}
        for future in concurrent.futures.as_completed(future_to_domain):
            result = future.result()
            if result:
                old, new = result
                replacements[old] = new
                print(f"Replacement found: {old} -> {new}")

    if not replacements:
        print("No dead domains found or no replacements found.")
        return

    # Apply replacements line by line with regex for safety
    lines = content.split('\n')
    new_lines = []

    for line in lines:
        if not line or line.startswith('!'):
            new_lines.append(line)
            continue

        modified_line = line
        for old, new in replacements.items():
            if old in line:
                # Regex replace:
                # Look for 'old' preceded by (start of line or non-word char)
                # and followed by (end of line or non-word char)
                # Actually for domains in adblock, they are usually surrounded by separators.
                # Separators: | ^ $ # /
                # But periods are word chars? No, periods are not word chars in \w usually?
                # Wait, \w includes [a-zA-Z0-9_]. Period is NOT \w.
                # So \b matches between . and a letter.
                # old = "example.com"
                # line = "||example.com^"
                # \bexample\.com\b match?
                # "||" is non-word. "e" is word. Match start.
                # "m" is word. "^" is non-word. Match end.
                # This works for "||example.com^".
                # What about "sub.example.com"? \b match at start of sub? No.
                # We need to replace the SPECIFIC string `old`.

                # Let's use re.escape(old) and lookahead/lookbehind or just boundary check based on adblock syntax.
                # A safer bet for adblock lines:
                # The domain usually appears after `||` or at start, or before `##` etc.
                # We simply want to ensure we don't replace `my-example.com` when replacing `example.com`.

                # Pattern: (?:^|[^a-zA-Z0-9\-\.])(old)(?:$|[^a-zA-Z0-9\-\.])
                # But we need to keep the groups.

                pattern = r'(^|[^a-zA-Z0-9\-\.])' + re.escape(old) + r'($|[^a-zA-Z0-9\-\.])'

                # Check if it matches
                if re.search(pattern, modified_line):
                    modified_line = re.sub(pattern, r'\1' + new + r'\2', modified_line)

        new_lines.append(modified_line)

    # Deduplicate lines
    # Preserve order, keep comments
    final_lines = []
    seen_lines = set()

    for line in new_lines:
        stripped = line.strip()
        # If it's a rule (not empty, not comment), check duplication
        if stripped and not stripped.startswith('!'):
            if stripped in seen_lines:
                continue
            seen_lines.add(stripped)
        final_lines.append(line)

    final_content = '\n'.join(final_lines)

    if final_content != content:
        with open(FILTER_FILE, 'w', encoding='utf-8') as f:
            f.write(final_content)
        print("Updated Yuusei.txt with new domains.")
    else:
        print("No changes made to file.")

if __name__ == "__main__":
    main()
