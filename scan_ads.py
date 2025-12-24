import argparse
import requests
from bs4 import BeautifulSoup
import re
import tldextract
from fake_useragent import UserAgent
import sys
from urllib.parse import urlparse

def get_known_ad_signatures(filter_file):
    """
    Parses the filter file to find known ad domains.
    """
    ad_domains = set()

    # Generic keywords often used in ad classes/IDs (English & Vietnamese)
    generic_keywords = [
        # English
        'ads', 'advert', 'advertising', 'banner', 'sponsor', 'promo', 'overlay',
        'popup', 'popunder', 'ad-box', 'ad-container', 'ad-wrapper', 'ad-slot',
        'google-auto-placed', 'adsbygoogle', 'taboola', 'outbrain', 'mgid',
        'partner', 'sticky-bottom', 'sticky-footer', 'floating-ads', 'catfish',
        'sidebar-ads', 'widget-ads', 'dynamic-ads',

        # Vietnamese
        'quangcao', 'quang-cao', 'qc', 'qc-float', 'tai-tro', 'doi-tac',
        'lien-ket', 'quang_cao', 'banner-doc', 'banner-ngang', 'qc_sticky'
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

def generate_ublock_rule(tag, attr, value, domain):
    """
    Generates a uBlock-style cosmetic rule.
    """
    # Prefer simple selectors if the value is clean
    # If value contains common separators like _, -, use partial match

    clean_value_pattern = re.compile(r'^[a-zA-Z0-9]+$')

    if clean_value_pattern.match(value):
        if attr == 'id':
            return f"{domain}###{value}"
        elif attr == 'class':
            return f"{domain}##.{value}"

    # For complex values, use attribute selector (uBlock style)
    # e.g. ##div[class*="banner-ads"]
    return f'{domain}##{tag}[{attr}*="{value}"]'

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

    # Use lxml for speed if available, else html.parser
    try:
        soup = BeautifulSoup(response.content, 'lxml')
    except:
        soup = BeautifulSoup(response.content, 'html.parser')

    domain_extract = tldextract.extract(url)
    site_domain = f"{domain_extract.domain}.{domain_extract.suffix}"
    if domain_extract.subdomain:
        site_domain = f"{domain_extract.subdomain}.{site_domain}"

    report_lines.append("## Findings")

    # 1. Heuristic: Check for Suspicious Class/ID Names
    print("Checking for suspicious class/id names...")

    # Exact words matching keywords, or containing them with delimiters
    # We want to match "ad-banner", "quangcao_top", but maybe not "leads" (if keyword is 'ad')
    # Let's simple check if the keyword is a substring for now, but be careful.

    suspicious_elements = []

    # Target specific layout/container tags to avoid false positives on small spans/links
    target_tags = ['div', 'section', 'aside', 'header', 'footer', 'iframe', 'img']

    for tag in soup.find_all(target_tags):
        tag_name = tag.name

        # Check ID
        element_id = tag.get('id')
        if element_id:
            for kw in generic_keywords:
                if kw.lower() in str(element_id).lower():
                    # Check if it looks like a real ad container
                    rule = generate_ublock_rule(tag_name, 'id', element_id, site_domain)
                    if rule not in new_rules:
                        suspicious_elements.append(f"- **Suspicious ID:** `{element_id}` (matched keyword '{kw}')")
                        new_rules.append(rule)
                    break # Only one rule per element needed

        # Check Classes
        classes = tag.get('class')
        if classes:
            if isinstance(classes, str): classes = [classes]
            for cls in classes:
                for kw in generic_keywords:
                    if kw.lower() in cls.lower():
                        rule = generate_ublock_rule(tag_name, 'class', cls, site_domain)
                        if rule not in new_rules:
                            suspicious_elements.append(f"- **Suspicious Class:** `{cls}` (matched keyword '{kw}')")
                            new_rules.append(rule)
                        break

    if suspicious_elements:
        report_lines.append("### Suspicious Elements (Keyword Match)")
        report_lines.extend(suspicious_elements)
        report_lines.append("")

    # 2. Heuristic: Check for External Resources from Known Ad Domains
    print("Checking for external ad resources...")
    resource_findings = []

    # Check for network requests (scripts, iframes, images)
    for tag_name in ['script', 'iframe', 'img', 'embed', 'object']:
        for tag in soup.find_all(tag_name):
            src = tag.get('src') or tag.get('data-src')
            if not src:
                continue

            src_extract = tldextract.extract(src)
            src_domain = f"{src_extract.domain}.{src_extract.suffix}"

            if not src_domain or src_domain == site_domain:
                continue

            # Check if this domain is known as an ad domain
            if src_domain in ad_domains:
                finding = f"- **Known Ad Resource:** `{src_domain}` found in `<{tag_name}>`."
                resource_findings.append(finding)

                # Rule Strategy:
                # 1. If it's a script, suggesting a network block rule for the domain might be aggressive if it serves other things.
                #    But if it's already in ad_domains, it should be blocked.
                #    If the user sees it, maybe the existing rule isn't working or it's a new subdomain.
                # 2. If it's a visual element (iframe, img), hide it physically.

                if tag_name in ['iframe', 'img', 'embed', 'object']:
                    # Cosmetic hiding based on source
                    # uBlock style: example.com##iframe[src*="doubleclick.net"]
                    rule = f'{site_domain}##{tag_name}[src*="{src_domain}"]'
                    if rule not in new_rules:
                        new_rules.append(rule)

                # Also suggest a network rule if it seems to be a specific ad server
                # that might not be fully covered (e.g. third-party script on this site)
                # ||src_domain^$domain=site_domain
                # This is "uBlock style" network filtering for 3rd party

                network_rule = f"||{src_domain}^$domain={site_domain}"
                if network_rule not in new_rules:
                     # Only add if we think it's useful.
                     # If src_domain is already in ad_domains, this rule is redundant BUT
                     # maybe the user wants to ensure it's blocked on THIS site specifically
                     # or maybe it wasn't caught by the general rule (e.g. different subdomain).
                     # Let's add it as a suggestion.
                     new_rules.append(network_rule)

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
        existing_lines = set(line.strip() for line in f)

    # Also check content just in case to detect file ending
    with open(filter_file, 'r', encoding='utf-8') as f:
        content = f.read()

    added_count = 0
    with open(filter_file, 'a', encoding='utf-8') as f:
        # Check if file ends with newline
        if content and not content.endswith('\n'):
            f.write('\n')

        # Group rules by type
        cosmetic_rules = [r for r in new_rules if '##' in r]
        network_rules = [r for r in new_rules if '##' not in r]

        if cosmetic_rules or network_rules:
             # Add a timestamp comment
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n! --- Auto-Scan Rules {timestamp} ---\n")

        for rule in network_rules:
            if rule not in existing_lines:
                f.write(f"{rule}\n")
                existing_lines.add(rule)
                added_count += 1
                print(f"Added network rule: {rule}")

        for rule in cosmetic_rules:
            if rule not in existing_lines:
                f.write(f"{rule}\n")
                existing_lines.add(rule)
                added_count += 1
                print(f"Added cosmetic rule: {rule}")

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
