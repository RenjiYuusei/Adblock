import re
import requests
import tldextract
from googlesearch import search
import concurrent.futures
import time
import sys

# Constants
FILTER_FILE = "Yuusei.txt"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
TIMEOUT = 10
MAX_WORKERS = 10  # Don't set too high to avoid rate limits

def get_unique_domains(content):
    """
    Extracts unique domains from the filter file content.
    Returns a set of domains.
    """
    domains = set()
    # Adblock syntax parsing logic
    # Handles:
    # ||example.com^
    # example.com##...
    # example.com#@#...
    # @@||example.com^

    # Regex for basic domain extraction
    # This captures the domain part from common adblock rules
    # It assumes the domain starts at the beginning or after options

    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('!'):
            continue

        # Remove Adblock operators like ||, @@||
        clean_line = re.sub(r'^(?:@@)?\|\|', '', line)

        # Split by separator to get the domain part ( separators: ^, $, #)
        parts = re.split(r'[\^\$\#\/]', clean_line)
        potential_domain = parts[0]

        # Validate if it looks like a domain
        if '.' in potential_domain and not '*' in potential_domain:
             # Basic sanity check (remove port, etc)
             domain = potential_domain.split(':')[0]
             # Trim trailing dots
             domain = domain.rstrip('.')

             # Extract main domain using tldextract to ensure validity
             ext = tldextract.extract(domain)
             if ext.domain and ext.suffix:
                 full_domain = f"{ext.subdomain}.{ext.domain}.{ext.suffix}".strip('.')
                 domains.add(full_domain)

    return domains

def check_domain_status(domain):
    """
    Checks if a domain is active.
    Returns True if active, False otherwise.
    """
    try:
        url = f"https://{domain}"
        response = requests.head(url, timeout=TIMEOUT, headers={'User-Agent': USER_AGENT}, allow_redirects=True)
        if response.status_code < 400:
            return True
    except (requests.ConnectionError, requests.Timeout):
        pass

    try:
        # Fallback to HTTP
        url = f"http://{domain}"
        response = requests.head(url, timeout=TIMEOUT, headers={'User-Agent': USER_AGENT}, allow_redirects=True)
        if response.status_code < 400:
            return True
    except:
        pass

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
        results = search(f"{brand} official site", num_results=5, advanced=True)

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
    except Exception as e:
        print(f"Search error for {dead_domain}: {e}")

    return None

def process_domain(domain):
    """
    Worker function to check a domain and find replacement if dead.
    Returns tuple (old_domain, new_domain) or None.
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

    # Check domains in parallel
    replacements = {}

    # For testing purposes, we might want to limit the number of domains checked if the list is huge
    # But checking 500 domains with 10 workers is fast enough.

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

    # Apply replacements
    new_content = content
    for old, new in replacements.items():
        # Simple string replace might be dangerous if 'old' is a substring of another domain
        # But given our extraction logic, it should be mostly fine.
        # Ideally we use regex to replace only word boundaries, but adblock syntax is messy.
        # We will try to replace specific patterns.

        print(f"Applying: {old} -> {new}")
        new_content = new_content.replace(old, new)

    # Deduplicate logic requested by user:
    # "các bộ lọc giống nhau về đuôi .com hay gì thi sẽ loại bỏ chỉ để lại 1 bộ lọc"
    # This is implicit: if we replaced animehay.life with animehay.vip, and animehay.vip already existed,
    # we now have duplicate rules. The user might want to remove exact duplicate lines.

    lines = new_content.split('\n')
    unique_lines = []
    seen_lines = set()

    for line in lines:
        stripped = line.strip()
        if stripped and stripped in seen_lines and not stripped.startswith('!'):
            continue # Skip duplicate
        if stripped and not stripped.startswith('!'):
            seen_lines.add(stripped)
        unique_lines.append(line)

    final_content = '\n'.join(unique_lines)

    if final_content != content:
        with open(FILTER_FILE, 'w', encoding='utf-8') as f:
            f.write(final_content)
        print("Updated Yuusei.txt with new domains.")
    else:
        print("No changes made to file.")

if __name__ == "__main__":
    main()
