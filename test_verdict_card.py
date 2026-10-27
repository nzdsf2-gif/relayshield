"""Shareable verdict card (approved 2026-10-24, text v1 only).

Covers the card builders and the send wiring in both webhooks:
  - Telegram _format_scan_verdict_card / _send_scan_verdict (/scan +
    deferred follow-up, checklist kept under the card on clean/unknown,
    Report-this button rides exactly as before).
  - Telegram _format_token_free_card + handle_checktoken free tier
    (paid tier _format_token_risk untouched).
  - WhatsApp build_verdict_response (SCAN + ATTACH URL paths).

No test here touches verdict logic: every expectation reuses the old
branches' inputs and checks only the card shape and copy rules (header,
badge, approved footer, forward line, no em dash, no 725K figure, never
a "safe" claim). The webhook modules are imported with the same boto3 /
botocore stubs test_verdict_gaps.py uses, since boto3 is not installed
in this environment.
"""

import pathlib
import sys
import types
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent


def _stub_aws():
    boto3 = types.ModuleType("boto3")
    boto3.__path__ = []
    boto3.resource = lambda *a, **k: unittest.mock.MagicMock()
    boto3.client = lambda *a, **k: unittest.mock.MagicMock()
    conditions = types.ModuleType("boto3.dynamodb.conditions")
    conditions.Key = lambda *a, **k: unittest.mock.MagicMock()
    conditions.Attr = lambda *a, **k: unittest.mock.MagicMock()
    dynamodb_mod = types.ModuleType("boto3.dynamodb")
    dynamodb_mod.__path__ = []
    dynamodb_mod.conditions = conditions
    boto3.dynamodb = dynamodb_mod
    sess = types.ModuleType("boto3.session")
    sys.modules.setdefault("boto3", boto3)
    sys.modules.setdefault("boto3.dynamodb", dynamodb_mod)
    sys.modules.setdefault("boto3.dynamodb.conditions", conditions)
    sys.modules.setdefault("boto3.session", sess)
    bc = types.ModuleType("botocore")
    bc.__path__ = []
    ex = types.ModuleType("botocore.exceptions")

    class _CE(Exception):
        pass

    ex.ClientError = _CE
    ex.BotoCoreError = _CE
    bc.exceptions = ex
    sys.modules.setdefault("botocore", bc)
    sys.modules.setdefault("botocore.exceptions", ex)


_stub_aws()
sys.path.insert(0, str(ROOT))
import relayshield_telegram_webhook as tg  # noqa: E402
import relayshield_whatsapp_webhook as wa  # noqa: E402

FOOTER = ("Checked against a growing threat intelligence corpus "
          "with over 129 monitored marketplaces.")


def _assert_card_rules(test, text):
    test.assertIn("🛡️ RelayShield Verdict", text)
    test.assertIn(FOOTER, text)
    test.assertNotIn("725K", text)
    test.assertNotIn("—", text)
    # Never a "safe" claim: "unsafe" (the unknown action) is allowed.
    test.assertNotIn("safe", text.lower().replace("unsafe", ""))


class TestTelegramScanCard(unittest.TestCase):
    def test_malicious(self):
        card = tg._format_scan_verdict_card(
            "evil-paypa1.com/login", "malicious",
            "3/70 security vendors flagged this URL as malicious")
        _assert_card_rules(self, card)
        self.assertIn("⛔ THREAT DETECTED", card)
        self.assertIn("Link: `evil-paypa1.com/login`", card)
        self.assertIn("Why: 3/70 security vendors flagged this URL as malicious.", card)
        self.assertIn("Do not click this link. Report it and delete the message", card)
        self.assertIn("[Forward this verdict by email](https://relayshield.net/forward?subject=", card)

    def test_suspicious(self):
        card = tg._format_scan_verdict_card(
            "x.com", "suspicious",
            "2/70 security vendors flagged this URL as suspicious")
        self.assertIn("⚠️ SUSPICIOUS", card)
        _assert_card_rules(self, card)

    def test_clean_keeps_caveat_and_sanitizes_vt_em_dash(self):
        card = tg._format_scan_verdict_card(
            "example.com", "clean",
            "Scanned by 70 security vendors — no threats found")
        self.assertIn("✅ NO FLAGS FOUND", card)
        self.assertIn("Why: Scanned by 70 security vendors: no threats found.", card)
        self.assertIn("That is not a guarantee: new scam pages appear daily.", card)
        _assert_card_rules(self, card)

    def test_unknown(self):
        card = tg._format_scan_verdict_card(
            "new.com", "unknown", "Not yet analyzed — submitted for scanning")
        self.assertIn("❓ UNCHECKED", card)
        self.assertIn("Treat this link as potentially unsafe until verified.", card)
        _assert_card_rules(self, card)

    def test_why_capped_at_two_reasons(self):
        card = tg._format_scan_verdict_card(
            "x.com", "suspicious", "Reason one; reason two; reason three")
        self.assertIn("Why: Reason one; reason two.", card)
        self.assertNotIn("reason three", card)

    def test_prefix_only_when_non_default(self):
        default = tg._format_scan_verdict_card("x.com", "clean", "d")
        self.assertNotIn("Scan result", default)
        follow = tg._format_scan_verdict_card(
            "x.com", "clean", "d", prefix="Follow-up scan result")
        self.assertIn("Follow-up scan result", follow)

    def test_send_keeps_checklist_on_clean_and_unknown(self):
        sent = []

        def fake_send(chat_id, text, parse_mode=None, reply_markup=None):
            sent.append((text, reply_markup))

        with unittest.mock.patch.object(tg, "send_message", fake_send):
            tg._send_scan_verdict(1, "example.com", "clean", "Scanned by 70 vendors")
            tg._send_scan_verdict(1, "new.com", "unknown", "Not yet analyzed")
            tg._send_scan_verdict(1, "evil.com", "malicious", "Flagged")
        clean, unknown, malicious = (s[0] for s in sent)
        for text in (clean, unknown):
            self.assertIn("Check the domain's registration date (whois)", text)
            self.assertIn("Still unsure? Don't click. Ask us.", text)
            _assert_card_rules(self, text)
        self.assertNotIn("whois", malicious)
        # Report button rides only via the flag-gated extras; disabled by
        # default, so no markup on any of the three sends.
        self.assertTrue(all(m is None for _, m in sent))

    def test_send_report_button_when_flag_on(self):
        sent = []

        def fake_send(chat_id, text, parse_mode=None, reply_markup=None):
            sent.append((text, reply_markup))

        patches = [
            unittest.mock.patch.object(
                tg.community_reports, "reports_enabled", lambda: True),
            unittest.mock.patch.object(
                tg.community_reports, "community_report_count", lambda *a: 0),
            unittest.mock.patch.object(
                tg.community_reports, "demand_side_label", lambda c: ""),
        ]
        for p in patches:
            p.start()
        try:
            with unittest.mock.patch.object(tg, "send_message", fake_send):
                tg._send_scan_verdict(1, "evil.com", "malicious", "Flagged")
        finally:
            for p in patches:
                p.stop()
        text, markup = sent[0]
        self.assertEqual(markup, tg.REPORT_BUTTON_MARKUP)
        self.assertIn("Report this", text)  # REPORT_HINT_TEXT rides after the card


class TestTelegramChecktokenCard(unittest.TestCase):
    def test_honeypot(self):
        card = tg._format_token_free_card("0x1a2b3c4d5e6f7890abcdef", "honeypot", 0.0)
        _assert_card_rules(self, card)
        self.assertIn("🚨 HIGH RISK: HONEYPOT", card)
        self.assertIn("Contract: `0x1a2b...cdef`", card)
        self.assertIn("Why: you cannot sell this token.", card)
        self.assertIn("⛔ Do NOT swap, approve, or interact with this token.", card)
        self.assertIn("[Forward this verdict by email](https://relayshield.net/forward?subject=", card)

    def test_scam_and_tax(self):
        scam = tg._format_token_free_card("0xabcdef0123456789", "scam", 0.0)
        self.assertIn("🚨 HIGH RISK: AIRDROP SCAM / FAKE TOKEN", scam)
        tax = tg._format_token_free_card("0xabcdef0123456789", "tax", 95.0)
        self.assertIn("🚨 HIGH RISK: SELL TAX 95%", tax)
        self.assertIn("Why: sell tax of 95% makes it effectively unsellable.", tax)
        _assert_card_rules(self, tax)

    def test_no_flags(self):
        card = tg._format_token_free_card("0xabcdef0123456789", None, 0.0)
        self.assertIn("✅ NO FLAGS FOUND", card)
        self.assertIn("No critical flags detected for this contract.", card)
        self.assertIn("That is not a guarantee", card)
        _assert_card_rules(self, card)

    def test_handle_checktoken_free_tier_wiring(self):
        sent = []

        def fake_send(chat_id, text, parse_mode=None, reply_markup=None):
            sent.append(text)

        honeypot = {"is_honeypot": "1", "is_airdrop_scam": "0",
                    "fake_token": "0", "sell_tax": 0}
        clean = {"is_honeypot": "0", "is_airdrop_scam": "0",
                 "fake_token": "0", "sell_tax": 0}
        with unittest.mock.patch.object(tg, "send_message", fake_send), \
                unittest.mock.patch.object(
                    tg, "_goplus_token_security", return_value=honeypot):
            tg.handle_checktoken(1, "0xabcdef0123456789", {"tier": "free"})
        self.assertIn("🚨 HIGH RISK: HONEYPOT", sent[1])
        self.assertIn("Crypto Shield", sent[1])  # upsell stays, free tier only
        sent.clear()
        with unittest.mock.patch.object(tg, "send_message", fake_send), \
                unittest.mock.patch.object(
                    tg, "_goplus_token_security", return_value=clean):
            tg.handle_checktoken(1, "0xabcdef0123456789", {"tier": "free"})
        self.assertIn("✅ NO FLAGS FOUND", sent[1])
        self.assertIn("Crypto Shield", sent[1])

    def test_paid_tier_unchanged(self):
        info = {"token_name": "T", "token_symbol": "T", "is_honeypot": "1"}
        self.assertIn("🔍 *Token Risk Check*", tg._format_token_risk("0xabcdef", info))
        self.assertNotIn("RelayShield Verdict", tg._format_token_risk("0xabcdef", info))


class TestWhatsAppCard(unittest.TestCase):
    def _stats(self, m=0, s=0, h=0, u=0):
        return {"malicious": m, "suspicious": s, "harmless": h, "undetected": u}

    def test_malicious(self):
        text = wa.build_verdict_response(
            self._stats(m=3, h=60, u=7), {"flagged": False},
            "that URL", "evil-paypa1.com/login")
        self.assertIn("⛔ THREAT DETECTED", text)
        self.assertIn("Why: 3 of 70 security engines confirmed a threat.", text)
        self.assertIn("Link: ```evil-paypa1.com/login```", text)
        _assert_card_rules(self, text)

    def test_vt_suspicious(self):
        text = wa.build_verdict_response(
            self._stats(s=2, h=60, u=8), {"flagged": False},
            "that URL", "x.com")
        self.assertIn("⚠️ SUSPICIOUS", text)
        self.assertIn("Why: 2 of 70 engines flagged as suspicious.", text)
        _assert_card_rules(self, text)

    def test_heuristic_only_still_suspicious(self):
        text = wa.build_verdict_response(
            self._stats(h=60, u=10), {"flagged": True,
                                     "reasons": ["on a blocklist", "domain is 2 days old"]},
            "that URL", "x.com")
        self.assertIn("⚠️ SUSPICIOUS", text)
        self.assertIn("On a blocklist; domain is 2 days old.", text)
        _assert_card_rules(self, text)

    def test_heuristic_reasons_capped_at_two(self):
        text = wa.build_verdict_response(
            self._stats(), {"flagged": True,
                            "reasons": ["one", "two", "three"]},
            "that URL", "x.com")
        self.assertIn("One; two.", text)
        self.assertNotIn("three", text)

    def test_clean_and_unchecked(self):
        clean = wa.build_verdict_response(
            self._stats(h=60, u=10), {"flagged": False}, "that URL", "example.com")
        self.assertIn("✅ NO FLAGS FOUND", clean)
        self.assertIn("Why: 70 of 70 engines found no threats.", clean)
        self.assertIn("That is not a guarantee", clean)
        _assert_card_rules(self, clean)
        unchecked = wa.build_verdict_response(
            None, {"flagged": False}, "that URL", "new.com")
        self.assertIn("❓ UNCHECKED", unchecked)
        self.assertIn("Treat it as potentially unsafe until verified.", unchecked)
        _assert_card_rules(self, unchecked)

    def test_target_label_fallback(self):
        text = wa.build_verdict_response(
            self._stats(h=60, u=10), {"flagged": False}, "that URL")
        self.assertIn("Link: ```that URL```", text)


if __name__ == "__main__":
    unittest.main()
