"""Unit tests for SSRF hardening: redirect chains and DNS rebinding.

Run: python3 -m unittest mcp_proxy.test_ssrf_hardening -v
"""

import unittest
from unittest import mock

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ssrf_hardening import (
    _check_dns_rebinding,
    _fetch_redirect_chain,
    check_url_with_hardening,
)


def _fake_is_internal(url, resolve=True):
    return "169.254.169.254" in url or "127.0.0.1" in url


def _fake_url_host(url):
    import urllib.parse
    return urllib.parse.urlsplit(url).hostname or ""


def _fake_resolve(host):
    return {"example.com": ["93.184.216.34"]}.get(host, [])


class TestFetchRedirectChain(unittest.TestCase):
    def test_no_redirect(self):
        with mock.patch("urllib.request.OpenerDirector.open") as m:
            # Simulate 200 OK (no exception).
            m.return_value = mock.MagicMock()
            chain = _fetch_redirect_chain("https://example.com/")
            self.assertEqual(chain, ["https://example.com/"])

    def test_single_redirect_to_internal(self):
        import urllib.error
        with mock.patch("urllib.request.OpenerDirector.open") as m:
            # First call: 302 to internal. Second: 200.
            err = urllib.error.HTTPError(
                "https://example.com/", 302, "Found", {}, None)
            err.headers = {"Location": "http://169.254.169.254/"}
            m.side_effect = [err, mock.MagicMock()]
            chain = _fetch_redirect_chain("https://example.com/")
            self.assertEqual(len(chain), 2)
            self.assertIn("169.254.169.254", chain[1])

    def test_max_redirects(self):
        import urllib.error
        with mock.patch("urllib.request.OpenerDirector.open") as m:
            def _redirect(*a, **k):
                err = urllib.error.HTTPError(
                    "https://example.com/", 302, "Found", {}, None)
                err.headers = {"Location": "https://example.com/next"}
                raise err
            m.side_effect = _redirect
            chain = _fetch_redirect_chain("https://example.com/",
                                          max_redirects=3)
            # Original + 3 hops.
            self.assertEqual(len(chain), 4)

    def test_relative_redirect(self):
        import urllib.error
        with mock.patch("urllib.request.OpenerDirector.open") as m:
            err = urllib.error.HTTPError(
                "https://example.com/a", 302, "Found", {}, None)
            err.headers = {"Location": "/b"}
            m.side_effect = [err, mock.MagicMock()]
            chain = _fetch_redirect_chain("https://example.com/a")
            self.assertEqual(chain[1], "https://example.com/b")


class TestDnsRebinding(unittest.TestCase):
    def test_no_rebinding(self):
        resolve = mock.Mock(return_value=["93.184.216.34"])
        self.assertFalse(_check_dns_rebinding("example.com", resolve))

    def test_rebinding_detected(self):
        resolve = mock.Mock(side_effect=[
            ["93.184.216.34"], ["127.0.0.1"],
        ])
        self.assertTrue(_check_dns_rebinding("evil.example", resolve))

    def test_empty_resolution(self):
        resolve = mock.Mock(return_value=[])
        self.assertFalse(_check_dns_rebinding("example.com", resolve))

    def test_resolver_error(self):
        resolve = mock.Mock(side_effect=OSError("dns down"))
        self.assertFalse(_check_dns_rebinding("example.com", resolve))


class TestCheckUrlWithHardening(unittest.TestCase):
    def test_direct_internal_blocked(self):
        r = check_url_with_hardening(
            "http://169.254.169.254/",
            _fake_is_internal, _fake_url_host, _fake_resolve,
            check_redirects=False, check_rebinding=False)
        self.assertTrue(r["blocked"])
        self.assertTrue(any("direct" in x for x in r["reasons"]))

    def test_redirect_to_internal_blocked(self):
        with mock.patch(
                "ssrf_hardening._fetch_redirect_chain",
                return_value=["https://example.com/",
                              "http://169.254.169.254/"]):
            r = check_url_with_hardening(
                "https://example.com/",
                _fake_is_internal, _fake_url_host, _fake_resolve,
                check_rebinding=False)
            self.assertTrue(r["blocked"])
            self.assertTrue(any("redirect" in x for x in r["reasons"]))

    def test_clean_url_allowed(self):
        with mock.patch(
                "ssrf_hardening._fetch_redirect_chain",
                return_value=["https://example.com/"]):
            r = check_url_with_hardening(
                "https://example.com/",
                _fake_is_internal, _fake_url_host, _fake_resolve)
            self.assertFalse(r["blocked"])

    def test_rebinding_blocked(self):
        with mock.patch(
                "ssrf_hardening._fetch_redirect_chain",
                return_value=["https://example.com/"]):
            with mock.patch(
                    "ssrf_hardening._check_dns_rebinding",
                    return_value=True):
                r = check_url_with_hardening(
                    "https://example.com/",
                    _fake_is_internal, _fake_url_host, _fake_resolve,
                    check_redirects=False)
                self.assertTrue(r["blocked"])
                self.assertTrue(any("rebinding" in x for x in r["reasons"]))

    def test_checks_disabled(self):
        r = check_url_with_hardening(
            "https://example.com/",
            _fake_is_internal, _fake_url_host, _fake_resolve,
            check_redirects=False, check_rebinding=False)
        self.assertFalse(r["blocked"])


if __name__ == "__main__":
    unittest.main()
