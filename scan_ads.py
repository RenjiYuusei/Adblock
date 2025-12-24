import argparse
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse
import tldextract
from collections import Counter

def get_common_selectors(filter_file):
    """
    Parses the filter file to find common element hiding selectors.
    """
    selectors = []
    ad_domains = set()

    with open(filter_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('!'):
                continue

            # Domain blocking rules
            if line.startswith('||'):
                parts = line[2:].split('^')
                domain = parts[0].split('/')[0]
                ad_domains.add(domain)

            # Element hiding rules
            if '##' in line:
                parts = line.split('##')
                if len(parts) == 2:
                    selector = parts[1]
                    # Filter out complex procedural cosmetic filters (start with +js, ^)
                    if not selector.startswith('+js') and not selector.startswith('^'):
                         selectors.append(selector)

    # Count frequency of selectors to find "common" ones
    # We can treat all selectors found in the file as "known ad patterns"
    # But checking thousands of selectors on a page might be slow.
    # For now, let's take the top 50 most common selectors, plus some hardcoded known ones if needed.
    # Actually, many rules are site specific.
    # Let's try to extract generic classes/ids from the selectors.

    # Simple heuristic: Split complex selectors and count class names / ids.
    # For this task, we will just try to match the exact selectors found in the file
    # against the target page, IF they are simple (classes/ids).

    simple_selectors = set()
    for s in selectors:
        # We focus on class and ID selectors for simplicity and performance
        if re.match(r'^[\.#][a-zA-Z0-9_\-]+$', s):
            simple_selectors.add(s)

    # Also add some very common ad selectors known in general
    common_generics = {
        '.ads', '.ad-banner', '.banner-ads', '.ad-box', '.advertisement',
        '#ads', '#banner', '.popup-ads', '.catfish', '.sticky-footer'
    }
    simple_selectors.update(common_generics)

    return simple_selectors, ad_domains

def scan_website(url, common_selectors, ad_domains):
    """
    Scans the website for ads using the common selectors and ad domains.
    """
    print(f"Scanning {url}...")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    new_rules = []

    domain_extract = tldextract.extract(url)
    domain = f"{domain_extract.domain}.{domain_extract.suffix}"
    if domain_extract.subdomain:
        domain = f"{domain_extract.subdomain}.{domain}"

    # 1. Check for elements matching common selectors
    print("Checking for ad elements...")
    for selector in common_selectors:
        try:
            elements = soup.select(selector)
            if elements:
                print(f"Found match for selector: {selector} ({len(elements)} elements)")
                rule = f"{domain}##{selector}"
                new_rules.append(rule)
        except Exception:
            continue # Ignore invalid selectors

    # 2. Check for external resources matching ad domains
    print("Checking for external ad resources...")
    resources = set()
    for tag in soup.find_all(['script', 'iframe', 'img', 'link']):
        src = tag.get('src') or tag.get('href')
        if src:
            # Check if it contains any known ad domain
            for ad_domain in ad_domains:
                if ad_domain in src:
                    print(f"Found resource matching ad domain {ad_domain}: {src}")
                    # We usually don't add rules for resources if the domain is already blocked globally.
                    # But if we want to block the specific element that loads it?
                    # Maybe we can suggest a network rule if it's a new domain.
                    # For now, let's focus on element hiding.
                    pass

    return list(set(new_rules))

def update_filter_list(filter_file, new_rules):
    """
    Updates the filter file with new rules.
    """
    if not new_rules:
        print("No new rules to add.")
        return False

    print(f"Adding {len(new_rules)} new rules to {filter_file}...")

    with open(filter_file, 'r', encoding='utf-8') as f:
        content = f.read()

    added_count = 0
    with open(filter_file, 'a', encoding='utf-8') as f:
        for rule in new_rules:
            if rule not in content:
                f.write(f"\n{rule}")
                added_count += 1
                print(f"Added: {rule}")
            else:
                print(f"Skipping existing rule: {rule}")

    return added_count > 0

def main():
    parser = argparse.ArgumentParser(description="Scan a website for ads and update filter list.")
    parser.add_argument("url", help="The URL of the website to scan")
    parser.add_argument("--filter-file", default="Yuusei.txt", help="Path to the filter list file")

    args = parser.parse_args()

    print(f"Loading rules from {args.filter_file}...")
    common_selectors, ad_domains = get_common_selectors(args.filter_file)
    print(f"Loaded {len(common_selectors)} common selectors and {len(ad_domains)} ad domains.")

    new_rules = scan_website(args.url, common_selectors, ad_domains)

    if update_filter_list(args.filter_file, new_rules):
        print("Filter list updated successfully.")
    else:
        print("No changes made to the filter list.")

if __name__ == "__main__":
    main()
