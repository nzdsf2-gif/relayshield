"""Shareable verdict card v1.1 delta (approved 2026-10-24), on top of v1.

Covers only the v1.1 changes; v1 behavior (card shape, checklist kept,
paid tier untouched, REPORT gating) is covered by test_verdict_card.py
and still runs unchanged.

  1. Per-bot link line in the card footer: Telegram cards link
     https://t.me/relayshield_bot, WhatsApp cards link
     https://wa.me/17407373961. Both handles were verified against the
     codebase before being baked in (Telegram @relayshield_bot;
     WA_QR_NUMBER 17407373961 in relayshield_developer_signup.py).
  2. Backticked target line: Telegram wraps Link/Contract in a
     single-backtick legacy-Markdown code span; WhatsApp wraps Link in
     a triple-backtick monospace span (the WhatsApp-native code span).
     Both close the flagged v1 residual: a URL carrying Markdown
     metacharacters cannot open an entity or break the send.
  3. Web-check line (v1.2, 2026-10-24): a "Try it on the web:
     https://relayshield.net/check" line below the bot link line, on
     the same free-tier cards only, so a forwarded card reaches
     recipients without Telegram or WhatsApp. Paid tier and the
     WhatsApp file-scan path carry neither line.

The metacharacter tests do not just assert string containment. They
strip the code spans out of the rendered card and assert the URL's
metacharacters appear NOWHERE outside a span, which is exactly what
"renders literally" means under both parsers.

Import stubs mirror test_verdict_card.py (boto3 is not installed here).
"""

import inspect
import pathlib
import re
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
TG_BOT_LINE = "[Try it yourself](https://t.me/relayshield_bot)"
WA_BOT_LINE = "Try it yourself: https://wa.me/17407373961"
WEBCHECK_LINE = "Try it on the web: https://relayshield.net/check"
# A URL carrying every legacy-Markdown/WhatsApp metacharacter that can
# open an entity: underscore, asterisk, brackets, tilde.
NASTY_URL = "https://evil.example.com/a_b*c[d]_e~f?x=1"


def _assert_v11_rules(test, text):
    test.assertIn(FOOTER, text)
    test.assertNotIn("725K", text)
    test.assertNotIn("—", text)
    test.assertNotIn("$", text)
    test.assertNotIn("safe", text.lower().replace("unsafe", ""))


class TestTelegramBotLinkLine(unittest.TestCase):
    def test_scan_card_links_tg_bot_after_forward_line(self):
        card = tg._format_scan_verdict_card(
            "evil-paypa1.com/login", "malicious",
            "3/70 security vendors flagged this URL as malicious.")
        self.assertIn(TG_BOT_LINE, card)
        self.assertLess(card.index("Forward this verdict by email"),
                        card.index(TG_BOT_LINE))
        _assert_v11_rules(self, card)

    def test_token_cards_link_tg_bot(self):
        for danger in ("honeypot", None):
            card = tg._format_token_free_card(
                "0x1a2b3c4d5e6f7890abcdef1234567890abcdef", danger, 0)
            self.assertIn(TG_BOT_LINE, card)
            self.assertLess(card.index("Forward this verdict by email"),
                            card.index(TG_BOT_LINE))
            _assert_v11_rules(self, card)

    def test_bot_link_constant_is_the_verified_handle(self):
        self.assertEqual(tg.CARD_BOT_LINK, TG_BOT_LINE)
        self.assertIn("@relayshield_bot", tg.BOT_HANDLE_MD)


class TestTelegramBacktickedTarget(unittest.TestCase):
    def test_metacharacter_url_renders_literally(self):
        card = tg._format_scan_verdict_card(
            NASTY_URL, "malicious",
            "3/70 security vendors flagged this URL as malicious.")
        link_line = [ln for ln in card.splitlines()
                     if ln.startswith("Link: ")][0]
        # The whole URL sits inside one code span, verbatim.
        self.assertEqual(link_line, f"Link: `{NASTY_URL}`")
        # Proof, not containment: strip code spans; no metacharacter
        # from the URL may survive outside one. Under legacy Markdown
        # a code span is literal, so nothing outside a span can open
        # an entity, and the span itself cannot break the send.
        outside = re.sub(r"`[^`]*`", "", card)
        for fragment in ("a_b", "*c", "[d]", "~f"):
            self.assertNotIn(fragment, outside)

    def test_backtick_in_target_cannot_close_the_span(self):
        card = tg._format_scan_verdict_card(
            "https://evil.example.com/a`b", "malicious", "flagged.")
        link_line = [ln for ln in card.splitlines()
                     if ln.startswith("Link: ")][0]
        self.assertEqual(link_line, "Link: `https://evil.example.com/a'b`")
        self.assertEqual(link_line.count("`"), 2)

    def test_token_contract_is_backticked(self):
        card = tg._format_token_free_card(
            "0x1a2b3c4d5e6f7890abcdef1234567890abcdef", "honeypot", 0)
        contract_line = [ln for ln in card.splitlines()
                         if ln.startswith("Contract: ")][0]
        self.assertEqual(contract_line, "Contract: `0x1a2b...cdef`")

    def test_span_is_never_nested_inside_a_bold_run(self):
        # Legacy Markdown does not nest a code span in bold (see
        # test_telegram_markdown_escapes.py). The card's Link/Contract
        # lines carry no bold markers at all.
        card = tg._format_scan_verdict_card(NASTY_URL, "malicious", "x.")
        for ln in card.splitlines():
            if ln.startswith(("Link: ", "Contract: ")):
                self.assertNotIn("*", ln.split("`")[0])


class TestWhatsAppBotLinkLine(unittest.TestCase):
    def test_scan_card_links_wa_bot_after_forward_line(self):
        card = wa.build_verdict_response(
            {"malicious": 3, "suspicious": 0, "harmless": 60,
             "undetected": 7},
            {"flagged": False, "reasons": []},
            "that URL", "https://evil.example.com/login")
        self.assertIn(WA_BOT_LINE, card)
        self.assertLess(card.index("Forward this verdict by email"),
                        card.index(WA_BOT_LINE))
        _assert_v11_rules(self, card)

    def test_bot_link_constant_is_the_verified_number(self):
        self.assertEqual(wa.WA_CARD_BOT_LINK, WA_BOT_LINE)


class TestTelegramWebcheckLine(unittest.TestCase):
    def test_scan_card_links_webcheck_after_bot_line(self):
        card = tg._format_scan_verdict_card(
            "evil-paypa1.com/login", "malicious",
            "3/70 security vendors flagged this URL as malicious.")
        self.assertIn(WEBCHECK_LINE, card)
        self.assertLess(card.index(TG_BOT_LINE), card.index(WEBCHECK_LINE))
        self.assertTrue(card.endswith(WEBCHECK_LINE))
        _assert_v11_rules(self, card)

    def test_token_cards_link_webcheck(self):
        for danger in ("honeypot", None):
            card = tg._format_token_free_card(
                "0x1a2b3c4d5e6f7890abcdef1234567890abcdef", danger, 0)
            self.assertIn(WEBCHECK_LINE, card)
            self.assertLess(card.index(TG_BOT_LINE),
                            card.index(WEBCHECK_LINE))
            self.assertTrue(card.endswith(WEBCHECK_LINE))
            _assert_v11_rules(self, card)

    def test_webcheck_constant_is_the_live_check_url(self):
        self.assertEqual(tg.CARD_WEBCHECK_LINK, WEBCHECK_LINE)


class TestWhatsAppWebcheckLine(unittest.TestCase):
    def test_scan_card_links_webcheck_after_bot_line(self):
        card = wa.build_verdict_response(
            {"malicious": 3, "suspicious": 0, "harmless": 60,
             "undetected": 7},
            {"flagged": False, "reasons": []},
            "that URL", "https://evil.example.com/login")
        self.assertIn(WEBCHECK_LINE, card)
        self.assertLess(card.index(WA_BOT_LINE), card.index(WEBCHECK_LINE))
        self.assertTrue(card.endswith(WEBCHECK_LINE))
        _assert_v11_rules(self, card)

    def test_webcheck_constant_is_the_live_check_url(self):
        self.assertEqual(wa.WA_CARD_WEBCHECK_LINK, WEBCHECK_LINE)


class TestWhatsAppBacktickedTarget(unittest.TestCase):
    def test_metacharacter_url_in_monospace_span(self):
        card = wa.build_verdict_response(
            {"malicious": 1, "suspicious": 0, "harmless": 0,
             "undetected": 0},
            {"flagged": False, "reasons": []},
            "that URL", NASTY_URL)
        link_line = [ln for ln in card.splitlines()
                     if ln.startswith("Link: ")][0]
        self.assertEqual(link_line, f"Link: ```{NASTY_URL}```")
        # Same literal-rendering proof as Telegram, against the
        # triple-backtick span: nothing from the URL survives outside.
        outside = re.sub(r"```.*?```", "", card)
        for fragment in ("a_b", "*c", "[d]", "~f"):
            self.assertNotIn(fragment, outside)

    def test_backtick_in_target_cannot_break_the_span(self):
        card = wa.build_verdict_response(
            None, {"flagged": False, "reasons": []},
            "that URL", "https://evil.example.com/a`b")
        link_line = [ln for ln in card.splitlines()
                     if ln.startswith("Link: ")][0]
        self.assertEqual(link_line, "Link: ```https://evil.example.com/a'b```")
        self.assertNotIn("`b`", link_line)


class TestV11LeavesV1RulesIntact(unittest.TestCase):
    def test_paid_token_tier_untouched_by_v11(self):
        src = inspect.getsource(tg._format_token_risk)
        self.assertNotIn("t.me/relayshield_bot", src)
        self.assertNotIn("CARD_BOT_LINK", src)
        self.assertNotIn("_card_code_span", src)

    def test_webcheck_line_absent_where_bot_link_is_absent(self):
        # Same scope as the bot link line: the paid checktoken tier
        # and the WhatsApp file-scan path never carried the bot link,
        # so they must not carry the web-check line either.
        src = inspect.getsource(tg._format_token_risk)
        self.assertNotIn("relayshield.net/check", src)
        self.assertNotIn("CARD_WEBCHECK_LINK", src)
        src = inspect.getsource(wa.build_vt_verdict_response)
        self.assertNotIn("relayshield.net/check", src)
        self.assertNotIn("WA_CARD_WEBCHECK_LINK", src)

    def test_v1_footer_and_forward_email_label(self):
        self.assertEqual(
            tg.CARD_FOOTER_CORPUS, FOOTER)
        self.assertEqual(
            wa.WA_CARD_FOOTER_CORPUS, FOOTER)
        self.assertEqual(
            tg.CARD_FORWARD_EMAIL_LABEL, "Forward this verdict by email")
        self.assertEqual(
            wa.WA_FORWARD_EMAIL_LABEL, "Forward this verdict by email")
        card = tg._format_scan_verdict_card(
            "evil-paypa1.com/login", "malicious",
            "3/70 security vendors flagged this URL as malicious")
        self.assertNotIn("Forward this verdict to anyone who received the same link.", card)
        token = tg._format_token_free_card("0xabcdef0123456789", "honeypot", 0.0)
        self.assertNotIn("Forward this verdict to anyone holding this token.", token)


if __name__ == "__main__":
    unittest.main()
