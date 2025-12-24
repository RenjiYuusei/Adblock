import argparse
import requests
from bs4 import BeautifulSoup
import re
import tldextract
from fake_useragent import UserAgent
import sys

def get_known_ad_signatures(filter_file):
    """
    Parses the filter file to find known ad domains and generic selectors.
    """
    ad_domains = set()

    # Generic keywords often used in ad classes/IDs
    generic_keywords = [
        'ads', 'banner', 'popup', 'sponsor', 'overlay', 'promo', 'ad-box',
        'ad-container', 'advertising', 'advert', 'ad-wrapper', 'catfish'
    ]

    try:
        with open(filter_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('!'):
                    continue

                # Extract domains from blocking rules like ||example.com^
                if line.startswith('||'):
                    parts = line[2:].split('^')
                    if parts:
                        domain = parts[0].split('/')[0]
                        ad_domains.add(domain)
    except FileNotFoundError:
        print(f"Warning: Filter file {filter_file} not found. Using default keywords only.")

    return ad_domains, generic_keywords

def scan_website(url, ad_domains, generic_keywords):
    """
    Scans the website for ads using heuristics and known ad domains.
    """
    print(f"Scanning {url}...")
    report_lines = [f"# Ad Scan Report for {url}", ""]
    new_rules = []

    try:
        ua = UserAgent()
        headers = {'User-Agent': ua.random}
        print(f"Using User-Agent: {headers['User-Agent']}")

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        error_msg = f"Error fetching {url}: {e}"
        print(error_msg)
        return [], [error_msg]

    soup = BeautifulSoup(response.content, 'html.parser')

    domain_extract = tldextract.extract(url)
    site_domain = f"{domain_extract.domain}.{domain_extract.suffix}"
    if domain_extract.subdomain:
        site_domain = f"{domain_extract.subdomain}.{site_domain}"

    report_lines.append("## Findings")

    # 1. Heuristic: Check for Suspicious Class/ID Names
    print("Checking for suspicious class/id names...")

    # Regex to match keywords as whole words or separated parts (e.g. 'top-banner', 'ads_box')
    # Case insensitive
    keyword_pattern = re.compile(r'[-_]?(?:' + '|'.join(generic_keywords) + r')(?:[-_0-9]|$)', re.IGNORECASE)

    suspicious_elements = []

    for element in soup.find_all(attrs={"class": True}) + soup.find_all(attrs={"id": True}):
        classes = element.get('class', [])
        if isinstance(classes, str): classes = [classes]
        element_id = element.get('id', '')

        identifier = None
        selector = None

        # Check ID first (stronger selector)
        if element_id and keyword_pattern.search(element_id):
            identifier = f'id="{element_id}"'
            selector = f'#{element_id}'
        # Check Classes
        elif classes:
            for cls in classes:
                if keyword_pattern.search(cls):
                    identifier = f'class="{cls}"'
                    selector = f'.{cls}'
                    break

        if selector:
            # Avoid adding rules for very short generic names if they might be valid content (e.g. 'promo' might be internal)
            # But for now, we list them.
            rule = f"{site_domain}##{selector}"
            if rule not in new_rules:
                suspicious_elements.append(f"- **Suspicious Element:** `{selector}` (matched {identifier})")
                new_rules.append(rule)

    if suspicious_elements:
        report_lines.append("### Suspicious Elements (Keyword Match)")
        report_lines.extend(suspicious_elements)
        report_lines.append("")

    # 2. Heuristic: Check for External Resources from Known Ad Domains
    print("Checking for external ad resources...")
    resource_findings = []

    # Check iframes, images, scripts
    for tag_name in ['iframe', 'img', 'script', 'a']:
        for tag in soup.find_all(tag_name):
            src = tag.get('src') or tag.get('href')
            if not src:
                continue

            # Extract domain from src
            src_extract = tldextract.extract(src)
            src_domain = f"{src_extract.domain}.{src_extract.suffix}"

            # Skip internal links
            if src_domain == site_domain or not src_domain:
                continue

            if src_domain in ad_domains:
                # Found a known ad domain
                finding = f"- **Known Ad Domain:** `{src_domain}` found in `<{tag_name}>` src/href."
                resource_findings.append(finding)

                # Generate a rule to hide this specific element if it's visual
                if tag_name in ['iframe', 'img']:
                    # Try to find a unique selector for this tag or its parent
                    # For simplicity, let's use src attribute matching if valid
                    # Rule: domain##iframe[src^="https://ad.com"]

                    # Truncate src to avoid super long rules, keep domain part
                    # Simplest valid rule: iframe[src*="ad.com"]
                    rule = f'{site_domain}##{tag_name}[src*="{src_domain}"]'
                    if rule not in new_rules:
                        new_rules.append(rule)

    if resource_findings:
        report_lines.append("### Known Ad Resources")
        report_lines.extend(resource_findings)
        report_lines.append("")

    if not new_rules:
        report_lines.append("No obvious ads found using current heuristics.")

    return list(set(new_rules)), report_lines

def update_filter_list(filter_file, new_rules):
    """
    Updates the filter file with new rules.
    """
    if not new_rules:
        return False

    print(f"Adding {len(new_rules)} new rules to {filter_file}...")

    with open(filter_file, 'r', encoding='utf-8') as f:
        content = f.read()

    added_count = 0
    with open(filter_file, 'a', encoding='utf-8') as f:
        f.write("\n") # Ensure newline
        for rule in new_rules:
            if rule not in content:
                f.write(f"{rule}\n")
                added_count += 1
                print(f"Added: {rule}")
            else:
                print(f"Skipping existing rule: {rule}")

    return added_count > 0

def main():
    parser = argparse.ArgumentParser(description="Scan a website for ads and update filter list.")
    parser.add_argument("url", help="The URL of the website to scan")
    parser.add_argument("--filter-file", default="Yuusei.txt", help="Path to the filter list file")
    parser.add_argument("--report-file", default="scan_report.md", help="Path to save the report")

    args = parser.parse_args()

    print(f"Loading knowledge from {args.filter_file}...")
    ad_domains, generic_keywords = get_known_ad_signatures(args.filter_file)
    print(f"Loaded {len(ad_domains)} known ad domains.")

    new_rules, report_lines = scan_website(args.url, ad_domains, generic_keywords)

    if update_filter_list(args.filter_file, new_rules):
        print("Filter list updated successfully.")
        report_lines.insert(0, f"✅ **Added {len(new_rules)} new rules** to `{args.filter_file}`.")
    else:
        print("No new unique rules found.")
        report_lines.insert(0, "ℹ️ No new rules were added (either no ads found or rules already exist).")

    # Write report
    with open(args.report_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    print(f"Report saved to {args.report_file}")

if __name__ == "__main__":
    main()
