"""Tests for the Telegram bot widget. No network, no dependencies.

    python3 test_relayshield_widget.py

Everything here is about the two promises in the module docstring: it never
raises, and it never says safe.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "widget"))

import relayshield_widget as w  # noqa: E402


def transport(response, *, raises=None):
    """Stub for the widget's _post. Records what it was called with."""
    calls = []

    def _t(url, payload, timeout, api_key):
        calls.append({"url": url, "payload": payload, "timeout": timeout, "api_key": api_key})
        if raises is not None:
            raise raises
        return response

    _t.calls = calls
    return _t


def link(level, reasons=()):
    return {"ok": True, "data": {"level": level, "reasons": list(reasons)}}


def wallet(risk_level, flags=()):
    return {"ok": True, "data": {"risk_level": risk_level, "risk_flags": list(flags)}}


class TestClassify(unittest.TestCase):
    def test_urls(self):
        for raw in ("https://a.example/x", "http://a.example", "a.example.com/path"):
            kind, norm = w.classify(raw)
            self.assertEqual(kind, "url", raw)
            self.assertTrue(norm.startswith("http"), norm)

    def test_bare_domain_gets_a_scheme(self):
        self.assertEqual(w.classify("scam-site.xyz")[1], "https://scam-site.xyz")

    def test_addresses(self):
        for raw in (
            "0x" + "a" * 40,                                   # EVM
            "EQ" + "A" * 46,                                   # TON
            "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",              # Bitcoin
            "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",    # Solana
        ):
            self.assertEqual(w.classify(raw)[0], "address", raw)

    def test_ronin_prefix_is_normalised_not_rejected(self):
        # The main Telegram bot rejects ronin:0x… — every wallet regex does.
        kind, norm = w.classify("ronin:0x" + "b" * 40)
        self.assertEqual(kind, "address")
        self.assertEqual(norm, "0x" + "b" * 40)

    def test_prose_is_unsupported(self):
        for raw in ("", "   ", "hello there", "check this out for me"):
            self.assertEqual(w.classify(raw)[0], "unsupported", repr(raw))


class TestRouting(unittest.TestCase):
    def test_url_goes_to_link_check_with_attribution(self):
        t = transport(link("high", ["listed"]))
        w.check("https://a.example", _transport=t)
        self.assertTrue(t.calls[0]["url"].endswith("/v1/link-check"))
        self.assertEqual(t.calls[0]["payload"]["source"], "tg-widget")

    def test_address_goes_to_wallet_risk(self):
        t = transport(wallet("LOW"))
        w.check("0x" + "c" * 40, _transport=t)
        self.assertTrue(t.calls[0]["url"].endswith("/v1/wallet-risk"))
        self.assertEqual(t.calls[0]["payload"]["address"], "0x" + "c" * 40)

    def test_unsupported_makes_no_call(self):
        t = transport(link("high"))
        v = w.check("just some words", _transport=t)
        self.assertEqual(t.calls, [])
        self.assertFalse(v.blocked)

    def test_api_key_is_passed_through(self):
        t = transport(link("unknown"))
        w.check("https://a.example", api_key="rs_live_x", _transport=t)
        self.assertEqual(t.calls[0]["api_key"], "rs_live_x")

    def test_default_timeout_suits_a_message_handler(self):
        t = transport(link("unknown"))
        w.check("https://a.example", _transport=t)
        self.assertLessEqual(t.calls[0]["timeout"], 5)


class TestNeverRaises(unittest.TestCase):
    def test_transport_exception_is_an_unchecked_verdict(self):
        for exc in (TimeoutError("slow"), ValueError("bad json"), OSError("dns")):
            v = w.check("https://a.example", _transport=transport(None, raises=exc))
            self.assertFalse(v.ok)
            self.assertEqual(v.level, "unknown")
            self.assertFalse(v.blocked)

    def test_error_envelope_is_not_a_pass(self):
        v = w.check("https://a.example",
                    _transport=transport({"ok": False, "error": "Daily limit reached"}))
        self.assertFalse(v.ok)
        self.assertFalse(v.blocked)

    def test_garbage_body_does_not_raise(self):
        for body in (None, [], "nope", {"data": {}}):
            v = w.check("https://a.example", _transport=transport(body))
            self.assertEqual(v.level, "unknown")

    def test_unknown_level_from_server_is_not_trusted(self):
        v = w.check("https://a.example", _transport=transport(link("SAFE")))
        self.assertEqual(v.level, "unknown")


class TestNeverSaysSafe(unittest.TestCase):
    def test_clean_url_text_carries_the_caveat(self):
        v = w.check("https://a.example", _transport=transport(link("unknown")))
        self.assertIn("not proof of safety", v.text)
        self.assertNotIn("safe.", v.text.lower().replace("not proof of safety", ""))

    def test_failed_check_says_unchecked_not_safe(self):
        v = w.check("https://a.example", _transport=transport(None, raises=OSError()))
        self.assertIn("did not complete", v.text)
        self.assertIn("not as safe", v.text)

    def test_failed_check_never_reads_as_a_pass_in_html_either(self):
        v = w.check("https://a.example", _transport=transport(None, raises=OSError()))
        self.assertIn("did not complete", v.html)


class TestBlocked(unittest.TestCase):
    def test_high_and_critical_block(self):
        for level in ("high", "critical"):
            self.assertTrue(w.check("https://a.example", _transport=transport(link(level))).blocked)

    def test_medium_warns_but_does_not_block(self):
        self.assertFalse(w.check("https://a.example", _transport=transport(link("medium"))).blocked)

    def test_wallet_clean_maps_to_low(self):
        v = w.check("0x" + "d" * 40, _transport=transport(wallet("CLEAN")))
        self.assertEqual(v.level, "low")
        self.assertFalse(v.blocked)

    def test_wallet_flags_are_readable(self):
        v = w.check("0x" + "e" * 40,
                    _transport=transport(wallet("HIGH", ["sanctions_hit", "high_tx_volume"])))
        self.assertTrue(v.blocked)
        self.assertIn("sanctions hit", v.reasons)


class TestTelegramMarkdown(unittest.TestCase):
    """Legacy Markdown has no escape syntax. These are the cases that broke it."""

    def test_underscores_in_a_url_stay_inside_a_code_span(self):
        url = "https://evil.example/reset_your_account_now"
        v = w.check(url, _transport=transport(link("high")))
        body = v.text.split("_Checked with")[0]
        self.assertIn(f"`{url}`", body)
        # No stray italic entity opened outside the code span.
        self.assertEqual(body.count("`") % 2, 0)

    def test_backticks_cannot_close_the_code_span(self):
        v = w.check("https://evil.example/`whoami`", _transport=transport(link("high")))
        self.assertNotIn("`whoami`", v.text.split("_Checked with")[0].replace("`https", ""))
        self.assertEqual(v.text.split("_Checked with")[0].count("`") % 2, 0)

    def test_html_escapes_angle_brackets(self):
        v = w.check("https://evil.example/<script>", _transport=transport(link("high")))
        self.assertIn("&lt;script&gt;", v.html)
        self.assertNotIn("<script>", v.html)

    def test_attribution_is_present_and_attributed(self):
        v = w.check("https://a.example", _transport=transport(link("unknown")))
        self.assertIn("source=tg-widget", v.text)
        self.assertIn("source=tg-widget", v.html)


if __name__ == "__main__":
    unittest.main(verbosity=1)
