"""Unit tests for protocol pivoting (SSRF) detection in the screener.

Run: python3 -m unittest mcp_proxy.test_ssrf -v
"""

import unittest
from unittest import mock

from mcp_proxy.screener import (
    POISON_SSRF,
    _is_internal_url,
    _parse_ip_literal,
    worst_category,
    Screener,
)


class TestParseIpLiteral(unittest.TestCase):
    def test_dotted_quad(self):
        self.assertEqual(str(_parse_ip_literal("127.0.0.1")), "127.0.0.1")

    def test_decimal_bypass(self):
        # 2130706433 == 127.0.0.1
        self.assertEqual(str(_parse_ip_literal("2130706433")), "127.0.0.1")

    def test_hex_bypass(self):
        self.assertEqual(str(_parse_ip_literal("0x7f.0.0.1")), "127.0.0.1")

    def test_octal_bypass(self):
        self.assertEqual(str(_parse_ip_literal("0177.0.0.1")), "127.0.0.1")

    def test_hostname_not_ip(self):
        self.assertIsNone(_parse_ip_literal("example.com"))

    def test_ipv6_loopback(self):
        self.assertEqual(str(_parse_ip_literal("::1")), "::1")


class TestIsInternalUrl(unittest.TestCase):
    def _check(self, url, **kwargs):
        kwargs.setdefault("resolve", False)
        return _is_internal_url(url, **kwargs)

    def test_metadata_endpoint(self):
        self.assertTrue(self._check(
            "http://169.254.169.254/latest/meta-data/"))

    def test_loopback(self):
        self.assertTrue(self._check("http://127.0.0.1:8080/admin"))

    def test_localhost(self):
        self.assertTrue(self._check("http://localhost:3000/api"))

    def test_private_10(self):
        self.assertTrue(self._check("http://10.0.5.12/internal"))

    def test_private_192_168(self):
        self.assertTrue(self._check("http://192.168.1.1/router"))

    def test_private_172_16(self):
        self.assertTrue(self._check("https://172.20.0.9:8443/"))

    def test_zero_network(self):
        self.assertTrue(self._check("http://0.0.0.0:80/"))

    def test_decimal_bypass(self):
        self.assertTrue(self._check("http://2130706433/"))

    def test_hex_bypass(self):
        self.assertTrue(self._check("http://0x7f.0.0.1/"))

    def test_ipv6_loopback(self):
        self.assertTrue(self._check("http://[::1]:8080/"))

    def test_private_suffix(self):
        self.assertTrue(self._check("http://db.internal:5432/"))

    def test_public_url_clean(self):
        self.assertFalse(self._check("https://api.relayshield.net/v1/check/url"))

    def test_public_ip_clean(self):
        self.assertFalse(self._check("http://93.184.216.34/"))

    def test_dns_resolves_private(self):
        with mock.patch(
                "mcp_proxy.screener._resolve_host_ips",
                return_value=["10.1.2.3"]):
            self.assertTrue(_is_internal_url("http://intranet.example/",
                                            resolve=True))

    def test_dns_resolves_public(self):
        with mock.patch(
                "mcp_proxy.screener._resolve_host_ips",
                return_value=["93.184.216.34"]):
            self.assertFalse(_is_internal_url("http://example.com/",
                                             resolve=True))

    def test_dns_failure_fails_open(self):
        with mock.patch(
                "mcp_proxy.screener._resolve_host_ips",
                side_effect=OSError("no resolver")):
            self.assertFalse(_is_internal_url("http://example.com/",
                                             resolve=True))


class TestSsrfVerdict(unittest.TestCase):
    def test_block_on_internal_url(self):
        s = Screener("https://api.example.invalid", ssrf_screening_enabled=True)
        verdict = s.screen_indicators(
            {"urls": ["http://169.254.169.254/latest/meta-data/"],
             "domains": [], "ips": []})
        self.assertEqual(verdict["verdict"], "block")
        self.assertEqual(verdict["poison_category"], POISON_SSRF)
        self.assertEqual(verdict["level"], "high")
        self.assertTrue(any(c.get("code") == "SSRF_INTERNAL_URL"
                            for c in verdict["cause_codes"]))

    def test_disabled_skips(self):
        s = Screener("https://api.example.invalid",
                     ssrf_screening_enabled=False)
        with mock.patch.object(s, "_check_url",
                               return_value={"level": "unknown", "score": 0,
                                             "reasons": []}):
            verdict = s.screen_indicators(
                {"urls": ["http://169.254.169.254/latest/meta-data/"],
                 "domains": [], "ips": []})
        self.assertNotEqual(verdict["poison_category"], POISON_SSRF)

    def test_ssrf_outranks_malicious_url(self):
        self.assertEqual(worst_category({"malicious_url", POISON_SSRF}),
                         POISON_SSRF)


if __name__ == "__main__":
    unittest.main()
