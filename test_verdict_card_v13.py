"""Verdict card v1.3 tests: the mailto forward link (2026-10-25).

v1.3 replaces the old forward text line with a tappable forward link
labeled "Forward this verdict by email". Telegram renders it as a
legacy-Markdown link to the relayshield.net/forward redirect, which
opens an email draft (a mailto: text_link is not tappable on iOS
Telegram). WhatsApp carries no link: plain-text messages have no
labeled-link syntax and the raw mailto: URL dumped percent-encoded
garbage, so the WhatsApp line is an instruction to long-press, tap
Forward, and pick a contact or group. Neither platform gets a real
button: Telegram url buttons accept HTTP or tg:// URLs only, and
WhatsApp CTA URL buttons cap the body at 1024 characters and the label
at 20 characters, while this bot sends plain-text session messages via
Twilio.

The email body is the card itself without the forward line; the subject
names the target (scan cards: the full URL; token cards: the short
address, first 6 plus last 4, as shown).
"""

import pathlib
import re
import sys
import types
import unittest
import unittest.mock
import urllib.parse

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
TG_BOT_LINE = "[Try it yourself](https://t.me/relayshield_bot)"
WA_BOT_LINE = "Try it yourself: https://wa.me/17407373961"
WEBCHECK_LINE = "Try it on the web: https://relayshield.net/check"
LABEL = "Forward this verdict by email"
WA_FORWARD_LINE = "Forward this verdict: long-press this message, tap Forward, and pick a contact or group to send it to."
NASTY_URL = "https://evil.example.com/a_b*c[d]_e~f?x=1"
OLD_SCAN_FORWARD = "Forward this verdict to anyone who received the same link."
OLD_TOKEN_FORWARD = "Forward this verdict to anyone holding this token."

# Characters that must never appear raw in a mailto URL: legacy-Markdown
# formatting (* _ [ ] ( ) `) and WhatsApp formatting (* _ ~).
_FORBIDDEN_IN_MAILTO = set("_*[]()`~")


def _tg_forward_url(card):
    match = re.search(r"\[Forward this verdict by email\]\((https://relayshield\.net/forward\?[^)]+)\)", card)
    assert match is not None, "Telegram forward Markdown link missing"
    return match.group(1)


def _mailto_parts(url):
    parts = urllib.parse.urlsplit(url)
    assert parts.scheme == "mailto" or (parts.scheme == "https" and parts.path == "/forward"), url
    assert parts.path in ("", "/forward"), url
    qs = urllib.parse.parse_qs(parts.query)
    return qs["subject"][0], qs["body"][0]


def _card_without_forward(card, prefix):
    return "\n".join([ln for ln in card.splitlines() if not ln.startswith(prefix)])


def _assert_no_standalone_safe(test, text):
    # "unsafe" (the unknown action) is allowed; standalone "safe" is not.
    test.assertIsNone(re.search(r"\bsafe\b", text, re.IGNORECASE))


class TestTelegramForwardLink(unittest.TestCase):
    def test_scan_forward_is_markdown_link(self):
        card = tg._format_scan_verdict_card(
            "evil-paypa1.com/login", "malicious",
            "3/70 security vendors flagged this URL as malicious")
        self.assertIn("[Forward this verdict by email](https://relayshield.net/forward?subject=", card)
        self.assertNotIn(OLD_SCAN_FORWARD, card)
        url = _tg_forward_url(card)
        self.assertTrue(url.startswith("https://relayshield.net/forward?subject="))

    def test_scan_mailto_round_trip(self):
        card = tg._format_scan_verdict_card(
            "evil-paypa1.com/login", "malicious",
            "3/70 security vendors flagged this URL as malicious")
        subject, body = _mailto_parts(_tg_forward_url(card))
        self.assertEqual(subject, "RelayShield verdict: evil-paypa1.com/login")
        self.assertEqual(body, _card_without_forward(card, "[Forward this verdict by email]("))
        self.assertIn(FOOTER, body)
        self.assertIn(TG_BOT_LINE, body)
        self.assertIn(WEBCHECK_LINE, body)
        self.assertNotIn(LABEL, body)

    def test_scan_mailto_encoding_special_chars(self):
        card = tg._format_scan_verdict_card(
            NASTY_URL, "malicious", "flagged; see https://x.example/?a=1&b=2")
        subject, body = _mailto_parts(_tg_forward_url(card))
        self.assertEqual(subject, "RelayShield verdict: " + NASTY_URL)
        self.assertEqual(body, _card_without_forward(card, "[Forward this verdict by email]("))
        self.assertIn(NASTY_URL, body)

    def test_scan_mailto_url_has_no_formatting_metacharacters(self):
        card = tg._format_scan_verdict_card(NASTY_URL, "malicious", "flagged")
        url = _tg_forward_url(card)
        self.assertEqual(set(url) & _FORBIDDEN_IN_MAILTO, set())
        self.assertNotIn(" ", url)

    def test_token_forward_uses_short_address(self):
        for danger in ("honeypot", "scam"):
            card = tg._format_token_free_card("0xabcdef0123456789", danger, 0.0)
            subject, body = _mailto_parts(_tg_forward_url(card))
            self.assertEqual(subject, "RelayShield verdict: 0xabcd...6789")
            self.assertEqual(body, _card_without_forward(card, "[Forward this verdict by email]("))
            self.assertNotIn(OLD_TOKEN_FORWARD, card)
        card = tg._format_token_free_card("0xabcdef0123456789", None, 0.0)
        subject, body = _mailto_parts(_tg_forward_url(card))
        self.assertEqual(subject, "RelayShield verdict: 0xabcd...6789")
        self.assertEqual(body, _card_without_forward(card, "[Forward this verdict by email]("))

    def test_scan_card_lines_otherwise_unchanged(self):
        card = tg._format_scan_verdict_card(
            "evil-paypa1.com/login", "malicious",
            "3/70 security vendors flagged this URL as malicious")
        self.assertEqual(
            _card_without_forward(card, "[Forward this verdict by email](").splitlines(),
            [tg.CARD_HEADER,
             "⛔ THREAT DETECTED",
             "",
             "Link: `evil-paypa1.com/login`",
             "Why: 3/70 security vendors flagged this URL as malicious.",
             "",
             "Do not click this link. Report it and delete the message if it was sent to you.",
             "",
             FOOTER,
             TG_BOT_LINE,
             WEBCHECK_LINE])

    def test_token_card_lines_otherwise_unchanged(self):
        card = tg._format_token_free_card("0xabcdef0123456789", None, 0.0)
        self.assertEqual(
            _card_without_forward(card, "[Forward this verdict by email](").splitlines(),
            [tg.CARD_HEADER,
             "✅ NO FLAGS FOUND",
             "",
             "Contract: `0xabcd...6789`",
             "No critical flags detected for this contract. That is not a guarantee: a token's risk profile can change.",
             "",
             FOOTER,
             TG_BOT_LINE,
             WEBCHECK_LINE])

    def test_no_standalone_safe_in_mailto_body(self):
        clean = tg._format_scan_verdict_card(
            "example.com", "clean", "Scanned by 70 security vendors, no threats found")
        _, body = _mailto_parts(_tg_forward_url(clean))
        _assert_no_standalone_safe(self, body)
        unknown = tg._format_scan_verdict_card("x.com", "unknown", "no data")
        _, body = _mailto_parts(_tg_forward_url(unknown))
        _assert_no_standalone_safe(self, body)

    def test_no_em_dash_in_forward_line(self):
        card = tg._format_scan_verdict_card("x.com", "malicious", "flagged")
        forward = [ln for ln in card.splitlines() if ln.startswith("[Forward this verdict by email](")][0]
        self.assertNotIn("\u2014", forward)

    def test_try_it_lines_unchanged_and_last(self):
        card = tg._format_scan_verdict_card("x.com", "malicious", "flagged")
        self.assertTrue(card.endswith(WEBCHECK_LINE))
        self.assertIn(TG_BOT_LINE, card)
        self.assertLess(card.index(LABEL), card.index(TG_BOT_LINE))
        self.assertLess(card.index(TG_BOT_LINE), card.index(WEBCHECK_LINE))


class TestWhatsAppForwardInstruction(unittest.TestCase):
    def test_forward_is_long_press_instruction(self):
        card = wa.build_verdict_response(
            {"malicious": 3, "suspicious": 0, "harmless": 40, "undetected": 27},
            {"flagged": False, "reasons": []}, "evil.example.com", target="https://evil.example.com/login")
        self.assertIn("Forward this verdict: long-press this message, tap Forward, and pick a contact or group to send it to.", card)
        self.assertNotIn("mailto:", card)
        self.assertNotIn(OLD_SCAN_FORWARD, card)

    def test_instruction_survives_nasty_target(self):
        card = wa.build_verdict_response(
            {"malicious": 3, "suspicious": 0, "harmless": 40, "undetected": 27},
            {"flagged": False, "reasons": []}, "evil.example.com", target=NASTY_URL)
        self.assertIn(WA_FORWARD_LINE, card)
        self.assertNotIn("mailto:", card)
        self.assertNotIn("%20", card)

    def test_card_lines_otherwise_unchanged(self):
        card = wa.build_verdict_response(
            {"malicious": 3, "suspicious": 0, "harmless": 40, "undetected": 27},
            {"flagged": False, "reasons": []}, "evil.example.com", target="https://evil.example.com/login")
        self.assertEqual(
            card.splitlines(),
            [wa.WA_CARD_HEADER,
             "⛔ THREAT DETECTED",
             "",
             "Link: ```https://evil.example.com/login```",
             "Why: 3 of 70 security engines confirmed a threat.",
             "",
             "Do not click this link. Delete the message if it was sent to you.",
             "",
             FOOTER,
             WA_FORWARD_LINE,
             WA_BOT_LINE,
             WEBCHECK_LINE])

    def test_no_em_dash_in_forward_line(self):
        card = wa.build_verdict_response(
            {"malicious": 3, "suspicious": 0, "harmless": 40, "undetected": 27},
            {"flagged": False, "reasons": []}, "evil.example.com", target="https://evil.example.com/login")
        forward = [ln for ln in card.splitlines() if ln.startswith("Forward this verdict:")][0]
        self.assertNotIn("\u2014", forward)

    def test_try_it_lines_unchanged_and_last(self):
        card = wa.build_verdict_response(
            {"malicious": 3, "suspicious": 0, "harmless": 40, "undetected": 27},
            {"flagged": False, "reasons": []}, "evil.example.com", target="https://evil.example.com/login")
        self.assertEqual(card.splitlines()[-1], WEBCHECK_LINE)
        self.assertIn(WA_BOT_LINE, card)
        self.assertLess(card.index(WA_FORWARD_LINE), card.index(WA_BOT_LINE))
        self.assertLess(card.index(WA_BOT_LINE), card.index(WEBCHECK_LINE))


def _markdown_safe(text):
    """Legacy-Markdown parse safety: strip link destinations and code
    spans, then no _ or * may remain. A lone _ (as in the old bare
    t.me/relayshield_bot URL) opens an italic entity Telegram rejects
    with 400 "can't parse entities", and the whole card never arrives."""
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    return "_" not in text and "*" not in text


class TestTelegramCardMarkdownSafe(unittest.TestCase):
    def test_scan_cards_markdown_safe(self):
        for verdict, reason in (
                ("malicious", "3/70 security vendors flagged this URL as malicious"),
                ("clean", "Scanned by 70 security vendors, no threats found"),
                ("unknown", "no data")):
            card = tg._format_scan_verdict_card("evil-paypa1.com/login", verdict, reason)
            self.assertTrue(_markdown_safe(card), card)

    def test_token_cards_markdown_safe(self):
        for danger in ("honeypot", "scam", None):
            card = tg._format_token_free_card("0xabcdef0123456789", danger, 0.0)
            self.assertTrue(_markdown_safe(card), card)


if __name__ == "__main__":
    unittest.main()
