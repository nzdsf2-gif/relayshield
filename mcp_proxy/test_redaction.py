"""Unit tests for PII redact-and-continue (screener.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_proxy.screener import (
    Screener,
    redact_text,
    redact_payload,
)

FAKE_EMAIL = "test@example.com"
FAKE_EMAIL2 = "other@example.org"
FAKE_PHONE = "555-010-1234"
FAKE_PHONE2 = "(555) 010-1234"
FAKE_SSN = "123-45-6789"
FAKE_CARD = "4111-1111-1111-1111"
FAKE_WALLET_ETH = "0x" + "a" * 40
FAKE_WALLET_SOL = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
FAKE_JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
FAKE_API_KEY = "sk-" + "x" * 48
FAKE_IP_FLAGGED = "203.0.113.45"
FAKE_IP_CLEAN = "192.0.2.1"


class TestRedactEmail(unittest.TestCase):
    def test_single_email(self):
        out, counts = redact_text(f"Contact {FAKE_EMAIL} for help.")
        self.assertEqual(out, "Contact [REDACTED_EMAIL] for help.")
        self.assertEqual(counts, {"email": 1})
        self.assertNotIn(FAKE_EMAIL, out)

    def test_multiple_emails(self):
        out, counts = redact_text(f"{FAKE_EMAIL} and {FAKE_EMAIL2}")
        self.assertEqual(counts, {"email": 2})

    def test_not_an_email(self):
        out, counts = redact_text("Visit example.com for info.")
        self.assertEqual(out, "Visit example.com for info.")
        self.assertEqual(counts, {})


class TestRedactPhone(unittest.TestCase):
    def test_dashed(self):
        out, counts = redact_text(f"Call {FAKE_PHONE}.")
        self.assertEqual(out, "Call [REDACTED_PHONE].")
        self.assertEqual(counts, {"phone": 1})

    def test_parenthesised(self):
        out, counts = redact_text(f"Call {FAKE_PHONE2}.")
        self.assertEqual(out, "Call [REDACTED_PHONE].")
        self.assertEqual(counts, {"phone": 1})

    def test_date_not_phone(self):
        out, counts = redact_text("Date 2026-11-14, version 1.2.3.")
        self.assertEqual(out, "Date 2026-11-14, version 1.2.3.")
        self.assertEqual(counts, {})


class TestRedactSSN(unittest.TestCase):
    def test_valid_ssn(self):
        out, counts = redact_text(f"SSN {FAKE_SSN} on file.")
        self.assertEqual(out, "SSN [REDACTED_SSN] on file.")
        self.assertEqual(counts, {"ssn": 1})

    def test_invalid_ssn_area(self):
        out, counts = redact_text("SSN 000-00-0000 is invalid.")
        self.assertEqual(out, "SSN 000-00-0000 is invalid.")
        self.assertEqual(counts, {})

    def test_invalid_ssn_666(self):
        out, counts = redact_text("SSN 666-11-2222 is invalid.")
        self.assertEqual(out, "SSN 666-11-2222 is invalid.")
        self.assertEqual(counts, {})


class TestRedactCard(unittest.TestCase):
    def test_luhn_valid(self):
        out, counts = redact_text(f"Card {FAKE_CARD} charged.")
        self.assertEqual(out, "Card [REDACTED_CARD] charged.")
        self.assertEqual(counts, {"card": 1})

    def test_luhn_invalid(self):
        out, counts = redact_text("Card 1234-5678-9012-3456 declined.")
        self.assertEqual(out, "Card 1234-5678-9012-3456 declined.")
        self.assertEqual(counts, {})

    def test_trailing_space_preserved(self):
        out, counts = redact_text(f"Card {FAKE_CARD} charged.")
        self.assertIn("[REDACTED_CARD] charged", out)


class TestRedactSecret(unittest.TestCase):
    def test_jwt(self):
        out, counts = redact_text(f"Token {FAKE_JWT} here.")
        self.assertNotIn(FAKE_JWT, out)
        self.assertEqual(counts.get("secret"), 1)

    def test_api_key(self):
        out, counts = redact_text(f"Key {FAKE_API_KEY} here.")
        self.assertNotIn(FAKE_API_KEY, out)
        self.assertEqual(counts.get("secret"), 1)


class TestRedactWallet(unittest.TestCase):
    def test_ethereum(self):
        out, counts = redact_text(f"Wallet {FAKE_WALLET_ETH} received.")
        self.assertEqual(out, "Wallet [REDACTED_WALLET] received.")
        self.assertEqual(counts, {"wallet": 1})

    def test_solana(self):
        out, counts = redact_text(f"Wallet {FAKE_WALLET_SOL} received.")
        self.assertEqual(out, "Wallet [REDACTED_WALLET] received.")
        self.assertEqual(counts, {"wallet": 1})

    def test_plain_word_not_wallet(self):
        out, counts = redact_text("The quick brown fox jumps.")
        self.assertEqual(out, "The quick brown fox jumps.")
        self.assertEqual(counts, {})


class TestRedactIP(unittest.TestCase):
    def test_flagged_ip_redacted(self):
        out, counts = redact_text(
            f"Server {FAKE_IP_FLAGGED} is malicious.",
            flagged_ips={FAKE_IP_FLAGGED})
        self.assertEqual(out, "Server [REDACTED_IP] is malicious.")
        self.assertEqual(counts, {"ip": 1})

    def test_clean_ip_not_redacted(self):
        out, counts = redact_text(
            f"Server {FAKE_IP_CLEAN} is fine.",
            flagged_ips={FAKE_IP_FLAGGED})
        self.assertEqual(out, f"Server {FAKE_IP_CLEAN} is fine.")
        self.assertEqual(counts, {})

    def test_no_flagged_set(self):
        out, counts = redact_text(f"Server {FAKE_IP_FLAGGED} here.")
        self.assertEqual(out, f"Server {FAKE_IP_FLAGGED} here.")
        self.assertEqual(counts, {})


class TestRedactPayload(unittest.TestCase):
    def test_nested(self):
        payload = {
            "tool": "lookup",
            "args": {"email": FAKE_EMAIL, "phone": FAKE_PHONE},
            "items": [FAKE_SSN, "clean text"],
        }
        out, counts = redact_payload(payload)
        self.assertEqual(out["args"]["email"], "[REDACTED_EMAIL]")
        self.assertEqual(out["args"]["phone"], "[REDACTED_PHONE]")
        self.assertEqual(out["items"][0], "[REDACTED_SSN]")
        self.assertEqual(out["items"][1], "clean text")
        self.assertEqual(
            counts, {"email": 1, "phone": 1, "ssn": 1})
        self.assertEqual(payload["args"]["email"], FAKE_EMAIL)

    def test_no_pii(self):
        payload = {"a": 1, "b": ["x", "y"]}
        out, counts = redact_payload(payload)
        self.assertEqual(out, payload)
        self.assertEqual(counts, {})

    def test_types_subset(self):
        out, counts = redact_payload(
            {"e": FAKE_EMAIL, "s": FAKE_SSN}, types={"email"})
        self.assertEqual(out["e"], "[REDACTED_EMAIL]")
        self.assertEqual(out["s"], FAKE_SSN)
        self.assertEqual(counts, {"email": 1})


class TestScreenToolResultRedaction(unittest.TestCase):
    def _screener(self, redaction_enabled=True):
        return Screener(api_base="https://api.example.invalid",
                        redaction_enabled=redaction_enabled)

    def test_result_redacted(self):
        s = self._screener()
        result = {"result": {"content": [{
            "type": "text",
            "text": f"Contact {FAKE_EMAIL}, SSN {FAKE_SSN}.",
        }]}}
        verdict = s.screen_tool_result(result)
        redacted = verdict["redacted_result"]
        text = redacted["result"]["content"][0]["text"]
        self.assertNotIn(FAKE_EMAIL, text)
        self.assertNotIn(FAKE_SSN, text)
        self.assertIn("[REDACTED_EMAIL]", text)
        self.assertIn("[REDACTED_SSN]", text)
        self.assertEqual(
            verdict["redactions"], {"email": 1, "ssn": 1})
        self.assertNotIn(FAKE_EMAIL, str(verdict))
        self.assertNotIn(FAKE_SSN, str(verdict))

    def test_redaction_off_default(self):
        s = Screener(api_base="https://api.example.invalid")
        self.assertFalse(s.redaction_enabled)
        result = {"result": {"content": [{
            "type": "text",
            "text": f"Contact {FAKE_EMAIL}.",
        }]}}
        verdict = s.screen_tool_result(result)
        text = verdict["redacted_result"]["result"]["content"][0]["text"]
        self.assertIn(FAKE_EMAIL, text)
        self.assertEqual(verdict["redactions"], {})

    def test_no_pii_clean(self):
        s = self._screener()
        result = {"result": {"content": [{
            "type": "text", "text": "Weather is sunny today.",
        }]}}
        verdict = s.screen_tool_result(result)
        self.assertEqual(verdict["verdict"], "clean")
        self.assertEqual(verdict["redactions"], {})


class TestScreenToolCallRedaction(unittest.TestCase):
    def test_arguments_redacted(self):
        s = Screener(api_base="https://api.example.invalid",
                     redaction_enabled=True)
        args = {"email": FAKE_EMAIL, "note": "hello"}
        verdict = s.screen_tool_call("lookup", args)
        redacted = verdict["redacted_arguments"]
        self.assertEqual(redacted["email"], "[REDACTED_EMAIL]")
        self.assertEqual(redacted["note"], "hello")
        self.assertEqual(verdict["redactions"], {"email": 1})
        self.assertNotIn(FAKE_EMAIL, str(verdict))

    def test_redaction_off(self):
        s = Screener(api_base="https://api.example.invalid")
        args = {"email": FAKE_EMAIL}
        verdict = s.screen_tool_call("lookup", args)
        self.assertNotIn("redacted_arguments", verdict)
        self.assertNotIn("redactions", verdict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
