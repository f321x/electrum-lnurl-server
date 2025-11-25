import re
from typing import Sequence

def normalize_url(raw_domain: str) -> str:
    assert raw_domain is not None, "provide a valid domain"
    # Remove protocol (http:// or https://)
    domain = re.sub(r'^https?://', '', raw_domain)
    # Remove www. prefix
    domain = re.sub(r'^www\.', '', domain)
    # Remove trailing slashes and whitespace
    domain = domain.rstrip('/ ')
    return domain

def normalize_websocket_urls(urls: Sequence[str]) -> list[str]:
    normalized = []
    for url in urls:
        url = url.strip().lower()
        if not url.startswith(('ws://', 'wss://')):
            url = 'wss://' + url
        if url.endswith('/'):
            url = url[:-1]
        normalized.append(url)
    return normalized

