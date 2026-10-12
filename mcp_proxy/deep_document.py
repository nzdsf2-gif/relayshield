"""Deep document validation for MCP Proxy Firewall.

Catches server-side SSRF via nested document references (e.g., OpenAPI
$ref pointing at cloud metadata). The proxy validates the initial document
URL, but the MCP server then dereferences embedded URLs using an unchecked
internal fetcher. This module extracts embedded URLs from fetched documents
and validates each against the SSRF blocklist.

Threat model: AWS OpenAPI MCP server (2026-10-11) - $ref bypass.
"""

import re
import json
import urllib.parse
import urllib.request
from html.parser import HTMLParser

# Reuse SSRF checks from screener
try:
    from .screener import _is_internal_url
except ImportError:
    # Fallback for standalone testing
    def _is_internal_url(url):
        return False, "not available"

# Constants
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10 MiB
MAX_EMBEDDED_URLS = 100
CACHE_TTL = 300  # 5 minutes

POISON_EMBEDDED_URL_SSRF = "embedded_url_ssrf"

# Simple in-memory cache
_validation_cache = {}


class _HrefExtractor(HTMLParser):
    """Extract href/src attributes from HTML."""
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ('href', 'src', 'action', 'data-src') and value:
                self.urls.append(value)


def _extract_openapi_refs(spec, base_url=""):
    """Recursively extract $ref values from OpenAPI spec."""
    refs = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == '$ref' and isinstance(v, str):
                    # Resolve relative refs against base
                    if base_url and not v.startswith(('http://', 'https://', '#')):
                        v = urllib.parse.urljoin(base_url, v)
                    # Skip fragment-only refs (#/components/...)
                    if not v.startswith('#'):
                        refs.append(v)
                elif k in ('url',) and isinstance(v, str) and v.startswith(('http://', 'https://')):
                    # servers[].url, externalDocs.url
                    refs.append(v)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(spec)
    return refs


def _extract_markdown_urls(text):
    """Extract URLs from Markdown links and images."""
    urls = []
    # [text](url) and ![alt](url)
    pattern = r'!?\[[^\]]*\]\(([^)]+)\)'
    for m in re.finditer(pattern, text):
        url = m.group(1).strip()
        # Remove title part: (url "title")
        url = url.split()[0].strip('<>')
        if url.startswith(('http://', 'https://')):
            urls.append(url)
    return urls


def _extract_generic_urls(text):
    """Fallback: extract all http(s) URLs from text."""
    pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    return re.findall(pattern, text)


def extract_embedded_urls(content, content_type="", base_url=""):
    """Extract embedded URLs from document content.
    
    Returns list of (url, source) tuples where source indicates
    where the URL was found ($ref, href, markdown, etc.).
    """
    urls = []

    content_type = content_type.lower()

    # Try JSON (OpenAPI, JSON Schema)
    if 'json' in content_type or content.strip().startswith('{'):
        try:
            spec = json.loads(content)
            for ref in _extract_openapi_refs(spec, base_url):
                urls.append((ref, '$ref'))
            return urls
        except (json.JSONDecodeError, ValueError):
            pass

    # Try YAML (OpenAPI) - basic check
    if 'yaml' in content_type or 'yml' in content_type:
        # For YAML, fall back to generic URL extraction
        # (full YAML parsing would require pyyaml)
        for url in _extract_generic_urls(content):
            urls.append((url, 'yaml-content'))
        return urls

    # Try HTML
    if 'html' in content_type or '<html' in content.lower()[:1000]:
        parser = _HrefExtractor()
        try:
            parser.feed(content)
            for url in parser.urls:
                if url.startswith(('http://', 'https://')):
                    urls.append((url, 'html-href'))
                elif url.startswith('/') and base_url:
                    # Resolve relative URLs
                    full = urllib.parse.urljoin(base_url, url)
                    urls.append((full, 'html-href-relative'))
            return urls
        except Exception:
            pass

    # Try Markdown
    if 'markdown' in content_type or '.md' in base_url:
        for url in _extract_markdown_urls(content):
            urls.append((url, 'markdown-link'))
        return urls

    # Fallback: generic URL extraction
    for url in _extract_generic_urls(content):
        urls.append((url, 'generic'))

    return urls


def fetch_document(url, timeout=10):
    """Fetch document with size cap.
    
    Returns (content, content_type) or (None, error).
    """
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'RelayShield-DeepDocValidator/1.0'
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get('Content-Type', '')
            # Read with size cap
            content = resp.read(MAX_DOCUMENT_SIZE + 1)
            if len(content) > MAX_DOCUMENT_SIZE:
                return None, f"document exceeds {MAX_DOCUMENT_SIZE} bytes"
            return content.decode('utf-8', errors='ignore'), content_type
    except Exception as e:
        return None, str(e)


def validate_document_urls(document_url, check_redirects=True):
    """Fetch document and validate all embedded URLs.
    
    Returns dict with:
    - verdict: "allow" | "block"
    - reasons: list of strings
    - embedded_urls: list of (url, source) found
    - blocked_urls: list of (url, source, reason) that failed validation
    """
    # Check cache
    import time
    cache_key = document_url
    if cache_key in _validation_cache:
        cached_time, cached_result = _validation_cache[cache_key]
        if time.time() - cached_time < CACHE_TTL:
            return cached_result

    result = {
        "verdict": "allow",
        "reasons": [],
        "embedded_urls": [],
        "blocked_urls": [],
        "document_url": document_url,
    }

    # Fetch document
    content, content_type_or_error = fetch_document(document_url)
    if content is None:
        # Fetch failed - fail open (log and allow)
        result["reasons"].append(f"document fetch failed: {content_type_or_error} (allowing)")
        _validation_cache[cache_key] = (time.time(), result)
        return result

    content_type = content_type_or_error

    # Extract embedded URLs
    embedded = extract_embedded_urls(content, content_type, document_url)
    # Cap to prevent DoS
    if len(embedded) > MAX_EMBEDDED_URLS:
        result["reasons"].append(
            f"document contains {len(embedded)} embedded URLs, "
            f"validating first {MAX_EMBEDDED_URLS}"
        )
        embedded = embedded[:MAX_EMBEDDED_URLS]

    result["embedded_urls"] = embedded

    # Validate each URL
    for url, source in embedded:
        is_internal, reason = _is_internal_url(url)
        if is_internal:
            result["verdict"] = "block"
            result["blocked_urls"].append((url, source, reason))
            result["reasons"].append(
                f"embedded_url_ssrf: {source} in document targets "
                f"internal infrastructure: {url} ({reason})"
            )

    _validation_cache[cache_key] = (time.time(), result)
    return result


def is_document_url(url):
    """Check if a URL looks like a document (vs API endpoint, etc.)."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()

    doc_extensions = (
        '.json', '.yaml', '.yml', '.html', '.htm',
        '.md', '.markdown', '.xml', '.txt'
    )

    # Check extension
    if any(path.endswith(ext) for ext in doc_extensions):
        return True

    # Check for common document URL patterns
    doc_patterns = [
        'openapi', 'swagger', 'schema', 'spec',
        '/docs/', '/documentation/'
    ]
    if any(p in path.lower() for p in doc_patterns):
        return True

    return False


def clear_cache():
    """Clear the validation cache (for testing)."""
    _validation_cache.clear()
