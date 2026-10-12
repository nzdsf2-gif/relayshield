"""Tests for deep document validation."""

import unittest
from unittest.mock import patch, MagicMock
import io

from .deep_document import (
    extract_embedded_urls,
    _extract_openapi_refs,
    _extract_markdown_urls,
    is_document_url,
    validate_document_urls,
    clear_cache,
    POISON_EMBEDDED_URL_SSRF,
)


class TestOpenAPIRefExtraction(unittest.TestCase):
    def test_simple_ref(self):
        spec = {
            "openapi": "3.0.0",
            "paths": {
                "/test": {
                    "get": {
                        "responses": {
                            "200": {
                                "$ref": "https://api.example.com/schema.json"
                            }
                        }
                    }
                }
            }
        }
        refs = _extract_openapi_refs(spec)
        self.assertIn("https://api.example.com/schema.json", refs)

    def test_nested_refs(self):
        spec = {
            "components": {
                "schemas": {
                    "User": {"$ref": "https://example.com/user.json"},
                    "Order": {
                        "properties": {
                            "user": {"$ref": "https://example.com/user.json"}
                        }
                    }
                }
            }
        }
        refs = _extract_openapi_refs(spec)
        self.assertEqual(len([r for r in refs if "user.json" in r]), 2)

    def test_fragment_ref_skipped(self):
        spec = {"$ref": "#/components/schemas/User"}
        refs = _extract_openapi_refs(spec)
        self.assertEqual(len(refs), 0)

    def test_relative_ref_resolved(self):
        spec = {"$ref": "./schemas/user.json"}
        refs = _extract_openapi_refs(spec, "https://api.example.com/openapi.json")
        self.assertIn("https://api.example.com/schemas/user.json", refs)

    def test_servers_url(self):
        spec = {
            "servers": [
                {"url": "https://api.example.com/v1"},
                {"url": "https://staging.example.com/v1"}
            ]
        }
        refs = _extract_openapi_refs(spec)
        self.assertIn("https://api.example.com/v1", refs)


class TestMarkdownExtraction(unittest.TestCase):
    def test_link(self):
        text = "See [docs](https://example.com/docs) for more"
        urls = _extract_markdown_urls(text)
        self.assertIn("https://example.com/docs", urls)

    def test_image(self):
        text = "![alt](https://example.com/img.png)"
        urls = _extract_markdown_urls(text)
        self.assertIn("https://example.com/img.png", urls)


class TestDocumentUrlDetection(unittest.TestCase):
    def test_json_extension(self):
        self.assertTrue(is_document_url("https://example.com/openapi.json"))

    def test_yaml_extension(self):
        self.assertTrue(is_document_url("https://example.com/spec.yaml"))

    def test_openapi_pattern(self):
        self.assertTrue(is_document_url("https://example.com/api/openapi"))

    def test_not_document(self):
        self.assertFalse(is_document_url("https://example.com/api/v1/users"))
        self.assertFalse(is_document_url("https://example.com/check"))


class TestExtractEmbeddedUrls(unittest.TestCase):
    def test_json_openapi(self):
        content = '{"openapi": "3.0.0", "paths": {"/x": {"get": {"responses": {"200": {"$ref": "https://evil.com/pwn.json"}}}}}}'
        urls = extract_embedded_urls(content, "application/json")
        self.assertTrue(any("evil.com" in u for u, s in urls))

    def test_html(self):
        content = '<html><body><img src="http://10.0.0.1/internal.png"><a href="https://example.com/">link</a></body></html>'
        urls = extract_embedded_urls(content, "text/html")
        url_list = [u for u, s in urls]
        self.assertIn("http://10.0.0.1/internal.png", url_list)
        self.assertIn("https://example.com/", url_list)


class TestValidateDocumentUrls(unittest.TestCase):
    def setUp(self):
        clear_cache()

    @patch('mcp_proxy.deep_document.fetch_document')
    @patch('mcp_proxy.deep_document._is_internal_url')
    def test_malicious_ref_blocked(self, mock_check, mock_fetch):
        # Simulate OpenAPI spec with $ref to metadata
        mock_fetch.return_value = (
            '{"$ref": "http://169.254.169.254/latest/meta-data/"}',
            'application/json'
        )
        mock_check.side_effect = lambda url: (
            (True, "cloud metadata") if "169.254.169.254" in url
            else (False, "public")
        )

        result = validate_document_urls("https://example.com/spec.json")
        self.assertEqual(result["verdict"], "block")
        self.assertTrue(any("169.254.169.254" in r for r in result["reasons"]))

    @patch('mcp_proxy.deep_document.fetch_document')
    @patch('mcp_proxy.deep_document._is_internal_url')
    def test_clean_spec_allowed(self, mock_check, mock_fetch):
        mock_fetch.return_value = (
            '{"openapi": "3.0.0", "$ref": "https://api.example.com/schema.json"}',
            'application/json'
        )
        mock_check.return_value = (False, "public")

        result = validate_document_urls("https://example.com/spec.json")
        self.assertEqual(result["verdict"], "allow")

    @patch('mcp_proxy.deep_document.fetch_document')
    def test_fetch_failure_allows(self, mock_fetch):
        mock_fetch.return_value = (None, "connection timeout")
        result = validate_document_urls("https://example.com/spec.json")
        self.assertEqual(result["verdict"], "allow")
        self.assertTrue(any("fetch failed" in r for r in result["reasons"]))


if __name__ == '__main__':
    unittest.main()
