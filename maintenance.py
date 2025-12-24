import re
import requests
import tldextract
from ddgs import DDGS
import concurrent.futures
import time
import sys

# Constants
FILTER_FILE = "Yuusei.txt"
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

        clean_line = re.sub(r'^(?:@@)?\|\|', '', line)
        parts = re.split(r'[\^\$\#\/]', clean_line)
        potential_domain = parts[0]

        if '.' in potential_domain and '*' not in potential_domain:
             domain = potential_domain.split(':')[0]
             domain = domain.rstrip('.')

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
            if response.status_code in [403, 401, 404, 500, 502, 503]:
                return True

        except (requests.ConnectionError, requests.Timeout):
            try:
                url = f"http://{domain}"
                response = requests.head(url, timeout=TIMEOUT, headers={'User-Agent': USER_AGENT}, allow_redirects=True)
                if response.status_code < 400:
                    return True
                if response.status_code in [403, 401, 404, 500, 502, 503]:
                    return True
            except:
                pass

        if attempt < RETRIES:
            time.sleep(2)

    return False

def search_domain_ddgs(query, brand, dead_domain, backend):
    """
    Searches using DDGS with specified backend.
    """
    try:
        print(f"[{backend}] Searching for: {query}")
        # DDGS().text supports backend argument
        results = DDGS().text(query, max_results=5, backend=backend)
        for result in results:
            url = result['href']
            res_ext = tldextract.extract(url)

            if res_ext.domain.lower() == brand.lower():
                new_domain = f"{res_ext.subdomain}.{res_ext.domain}.{res_ext.suffix}".strip('.')
                if new_domain != dead_domain and check_domain_status(new_domain):
                    return new_domain
    except Exception as e:
        print(f"[{backend}] Error: {e}")
    return None

def find_replacement_domain(dead_domain):
    """
    Searches for a replacement domain using DDGS (DuckDuckGo then Google).
    """
    ext = tldextract.extract(dead_domain)
    brand = ext.domain
    if not brand:
        return None

    print(f"Searching for replacement for dead domain: {dead_domain} (Brand: {brand})")

    query = f"{brand} official site"

    # Try DuckDuckGo first (default or explicit 'duckduckgo')
    # According to docs, backend="auto" or "duckduckgo"
    replacement = search_domain_ddgs(query, brand, dead_domain, backend="duckduckgo")
    if replacement:
        print(f"Found replacement via DDG: {replacement}")
        return replacement

    # Fallback to Google via DDGS
    replacement = search_domain_ddgs(query, brand, dead_domain, backend="google")
    if replacement:
        print(f"Found replacement via Google: {replacement}")
        return replacement

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
    print("Starting domain maintenance (DDGS Only)...")

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
                print(f"Replacement confirmed: {old} -> {new}")

    if not replacements:
        print("No dead domains found or no replacements found.")
        return

    # Apply replacements
    lines = content.split('\n')
    new_lines = []

    for line in lines:
        if not line or line.startswith('!'):
            new_lines.append(line)
            continue

        modified_line = line
        for old, new in replacements.items():
            if old in line:
                pattern = r'(^|[^a-zA-Z0-9\-\.])' + re.escape(old) + r'($|[^a-zA-Z0-9\-\.])'
                if re.search(pattern, modified_line):
                    modified_line = re.sub(pattern, r'\1' + new + r'\2', modified_line)

        new_lines.append(modified_line)

    # Deduplication
    final_lines = []
    seen_lines = set()

    for line in new_lines:
        stripped = line.strip()
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
