import re

def normalize_url(raw_domain: str) -> str:
    assert raw_domain is not None, "provide a valid domain"
    # Remove protocol (http:// or https://)
    domain = re.sub(r'^https?://', '', raw_domain)
    # Remove www. prefix
    domain = re.sub(r'^www\.', '', domain)
    # Remove trailing slashes and whitespace
    domain = domain.rstrip('/ ')
    return domain

