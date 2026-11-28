"""Unit tests for mcp_proxy.fingerprint.

Stdlib unittest only; the module has no package imports, so these run
standalone against the new file without the rest of the proxy:

    python3 -m unittest discover -s mcp_proxy -p "test_fingerprint.py" -v

Run from ~/workspace/builds/firewall-fingerprinting/.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fingerprint import (  # noqa: E402
    FingerprintStore,
    compute_fingerprint,
    denylist_token_ok,
    extract_attributes,
    fingerprint_for_request,
    network_hash,
)


class _FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class TestComputeFingerprint(unittest.TestCase):
    def test_deterministic(self):
        attrs = {"agent_id": "agent-1", "client_name": "claude",
                 "client_version": "1.2.3", "user_agent": "Claude/1.2.3"}
        self.assertEqual(compute_fingerprint(attrs),
                         compute_fingerprint(attrs))
        self.assertEqual(len(compute_fingerprint(attrs)), 64)

    def test_empty_attributes_give_empty_fingerprint(self):
        self.assertEqual(compute_fingerprint({}), "")
        self.assertEqual(compute_fingerprint({"agent_id": "  "}), "")

    def test_field_change_changes_fingerprint(self):
        a = {"agent_id": "agent-1", "client_name": "claude"}
        b = {"agent_id": "agent-2", "client_name": "claude"}
        self.assertNotEqual(compute_fingerprint(a), compute_fingerprint(b))

    def test_salt_changes_fingerprint(self):
        attrs = {"agent_id": "agent-1"}
        self.assertNotEqual(compute_fingerprint(attrs, salt=""),
                            compute_fingerprint(attrs, salt="s3cret"))

    def test_blank_values_dropped(self):
        a = {"agent_id": "agent-1", "client_name": ""}
        b = {"agent_id": "agent-1"}
        self.assertEqual(compute_fingerprint(a), compute_fingerprint(b))


class TestNetworkHash(unittest.TestCase):
    def test_domain_separated_from_identity(self):
        # Same raw value must not produce the same hash in the two
        # domains: a network hash must never equal an identity hash.
        self.assertNotEqual(network_hash("10.0.0.1", salt="s"),
                            compute_fingerprint({"agent_id": "10.0.0.1"},
                                                salt="s"))

    def test_deterministic_and_empty_safe(self):
        self.assertEqual(network_hash("10.0.0.1"),
                         network_hash("10.0.0.1"))
        self.assertEqual(network_hash(""), "")


class TestExtractAttributes(unittest.TestCase):
    def test_initialize_inline_client_info_preferred(self):
        req = {"params": {"protocolVersion": "2026-07-28",
                          "clientInfo": {"name": "live-client",
                                         "version": "9.9"}}}
        attrs = extract_attributes(
            req, _FakeHeaders({"User-Agent": "UA/1"}),
            client_info={"name": "stored", "version": "1.0",
                         "protocol_version": "old"})
        self.assertEqual(attrs["client_name"], "live-client")
        self.assertEqual(attrs["client_version"], "9.9")
        self.assertEqual(attrs["protocol_version"], "2026-07-28")
        self.assertEqual(attrs["user_agent"], "UA/1")

    def test_remembered_client_info_used_for_tools_call(self):
        req = {"params": {"name": "check_link"},
               "_rs_agent_id": "agent-7"}
        attrs = extract_attributes(
            req, _FakeHeaders({"User-Agent": "Claude/2.0"}),
            client_info={"name": "claude-desktop", "version": "2.0",
                         "protocol_version": "2026-07-28"})
        self.assertEqual(attrs["agent_id"], "agent-7")
        self.assertEqual(attrs["client_name"], "claude-desktop")
        self.assertEqual(attrs["protocol_version"], "2026-07-28")

    def test_fingerprint_for_request_label_truncated(self):
        req = {"params": {},
               "_rs_agent_id": "agent-1"}
        out = fingerprint_for_request(
            req, _FakeHeaders({"User-Agent": "x" * 200}),
            "10.0.0.1",
            client_info={"name": "n" * 100, "version": "1.0"})
        self.assertEqual(len(out["fingerprint"]), 64)
        self.assertEqual(len(out["network"]), 64)
        self.assertLessEqual(len(out["label"]), 64)


class TestFingerprintStore(unittest.TestCase):
    def test_observe_then_check_clean(self):
        store = FingerprintStore()
        fp = compute_fingerprint({"agent_id": "a1"})
        store.observe(fp, tenant_id="tnt_1", network="net1",
                      label="claude 1.0")
        got = store.check(fp)
        self.assertEqual(got["status"], "clean")
        self.assertEqual(got["call_count"], 1)
        rec = store.lookup(fp)
        self.assertEqual(rec["tenants"], ["tnt_1"])
        self.assertEqual(rec["networks"], ["net1"])
        self.assertEqual(rec["client_labels"], ["claude 1.0"])

    def test_unknown_fingerprint(self):
        store = FingerprintStore()
        self.assertEqual(
            store.check(compute_fingerprint({"agent_id": "nope"}))["status"],
            "unknown")

    def test_flag_then_unflag(self):
        store = FingerprintStore()
        fp = compute_fingerprint({"agent_id": "a2"})
        store.observe(fp)
        store.flag(fp, "behavior:attack_chain", tool_name="fetch_page",
                   tenant_id="tnt_1")
        got = store.check(fp)
        self.assertEqual(got["status"], "flagged")
        self.assertEqual(len(got["flags"]), 1)
        self.assertEqual(got["flags"][0]["reason"],
                         "behavior:attack_chain")
        store.unflag(fp, "operator review: false positive")
        self.assertEqual(store.check(fp)["status"], "clean")

    def test_flag_without_prior_observe(self):
        store = FingerprintStore()
        fp = compute_fingerprint({"agent_id": "a3"})
        store.flag(fp, "ti_block:high")
        self.assertEqual(store.check(fp)["status"], "flagged")
        self.assertEqual(store.lookup(fp)["call_count"], 0)

    def test_disabled_store_is_noop(self):
        store = FingerprintStore(enabled=False)
        fp = compute_fingerprint({"agent_id": "a4"})
        self.assertEqual(store.observe(fp), {})
        self.assertEqual(store.flag(fp, "x"), {})
        self.assertEqual(store.check(fp), {})

    def test_empty_fingerprint_is_noop(self):
        store = FingerprintStore()
        self.assertEqual(store.observe(""), {})
        self.assertEqual(store.flag("", "x"), {})

    def test_summary_counts_flagged(self):
        store = FingerprintStore()
        f1 = compute_fingerprint({"agent_id": "s1"})
        f2 = compute_fingerprint({"agent_id": "s2"})
        store.observe(f1)
        store.observe(f2)
        store.flag(f2, "kill_chain:flag")
        summary = store.summary()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["flagged"], 1)
        self.assertEqual(summary["flagged_fingerprints"][0]["fingerprint"],
                         f2)


class TestFingerprintPersistence(unittest.TestCase):
    def test_round_trip_through_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "fingerprints.jsonl")
            store = FingerprintStore(path=path, salt="testsalt")
            fp = compute_fingerprint({"agent_id": "p1"}, salt="testsalt")
            store.observe(fp, tenant_id="tnt_9", network="net9",
                          label="claude 1.0")
            store.observe(fp, tenant_id="tnt_9", network="net9")
            store.flag(fp, "behavior:attack_chain", tool_name="run_cmd")
            # Fresh instance replays the file.
            store2 = FingerprintStore(path=path, salt="testsalt")
            got = store2.check(fp)
            self.assertEqual(got["status"], "flagged")
            self.assertEqual(got["call_count"], 2)
            self.assertEqual(got["flags"][0]["reason"],
                             "behavior:attack_chain")
            rec = store2.lookup(fp)
            self.assertEqual(rec["tenants"], ["tnt_9"])

    def test_no_raw_pii_at_rest(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "fingerprints.jsonl")
            store = FingerprintStore(path=path, salt="testsalt")
            req = {"params": {"name": "check_link"},
                   "_rs_agent_id": "agent-secret-123"}
            out = fingerprint_for_request(
                req, _FakeHeaders(
                    {"User-Agent": "SecretAgent/9.9 (internal-build)"}),
                "203.0.113.77")
            store.observe(out["fingerprint"], network=out["network"],
                          label=out["label"])
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            self.assertNotIn("203.0.113.77", raw)
            self.assertNotIn("SecretAgent", raw)
            self.assertNotIn("agent-secret-123", raw)
            # Only hashes and the truncated product label are stored.
            self.assertIn(out["fingerprint"], raw)

    def test_compact_preserves_state(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "fingerprints.jsonl")
            store = FingerprintStore(path=path)
            f1 = compute_fingerprint({"agent_id": "c1"})
            f2 = compute_fingerprint({"agent_id": "c2"})
            store.observe(f1)
            store.observe(f2)
            store.flag(f2, "ti_block:high")
            self.assertTrue(store.compact())
            store2 = FingerprintStore(path=path)
            self.assertEqual(store2.check(f1)["status"], "clean")
            self.assertEqual(store2.check(f1)["call_count"], 1)
            self.assertEqual(store2.check(f2)["status"], "flagged")
            self.assertEqual(store2.check(f2)["call_count"], 1)
            # File is now one snapshot line per fingerprint.
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
            self.assertEqual(len(lines), 2)
            self.assertTrue(all(
                json.loads(ln)["type"] == "snapshot" for ln in lines))


class TestFingerprintDenylist(unittest.TestCase):
    def _fp(self, tag):
        return compute_fingerprint({"agent_id": tag})

    def test_denylisted_fingerprint_matches(self):
        store = FingerprintStore()
        fp = self._fp("bad-1")
        self.assertIsNone(store.is_denylisted(fp))
        entry = store.denylist_add(fp, "operator: stolen session",
                                   added_by="andrew")
        self.assertEqual(entry["fingerprint"], fp)
        self.assertEqual(entry["reason"], "operator: stolen session")
        got = store.is_denylisted(fp)
        self.assertIsNotNone(got)
        self.assertEqual(got["reason"], "operator: stolen session")

    def test_non_denylisted_fingerprint_does_not_match(self):
        # Flag-only: a flagged fingerprint is NOT denylisted, and a
        # clean one is not either. Only an explicit denylist add
        # makes is_denylisted() return an entry (the condition the
        # proxy uses to block).
        store = FingerprintStore()
        flagged = self._fp("flagged-1")
        clean = self._fp("clean-1")
        store.flag(flagged, "behavior:attack_chain")
        self.assertEqual(store.check(flagged)["status"], "flagged")
        self.assertIsNone(store.is_denylisted(flagged))
        self.assertIsNone(store.is_denylisted(clean))

    def test_empty_denylist_never_blocks(self):
        store = FingerprintStore()
        for tag in ("x", "y", "z"):
            self.assertIsNone(store.is_denylisted(self._fp(tag)))
        self.assertEqual(store.denylist_list(), [])
        self.assertEqual(store.denylist_reload(), 0)

    def test_missing_denylist_file_never_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "no-such-denylist.json")
            store = FingerprintStore(denylist_path=path)
            self.assertIsNone(store.is_denylisted(self._fp("m1")))
            self.assertEqual(store.denylist_list(), [])

    def test_denylist_remove_unblocks(self):
        store = FingerprintStore()
        fp = self._fp("bad-2")
        store.denylist_add(fp, "r")
        self.assertIsNotNone(store.is_denylisted(fp))
        self.assertTrue(store.denylist_remove(fp))
        self.assertIsNone(store.is_denylisted(fp))
        self.assertFalse(store.denylist_remove(fp))

    def test_denylist_rejects_invalid_fingerprint(self):
        store = FingerprintStore()
        self.assertEqual(store.denylist_add("not-a-hash", "r"), {})
        self.assertEqual(store.denylist_add("a" * 63, "r"), {})
        self.assertEqual(store.denylist_add("", "r"), {})
        self.assertFalse(store.denylist_remove("not-a-hash"))
        self.assertEqual(store.denylist_list(), [])

    def test_denylist_persists_to_file_and_reloads(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "fingerprints_denylist.json")
            store = FingerprintStore(denylist_path=path)
            fp = self._fp("bad-3")
            store.denylist_add(fp, "stolen session")
            # Fresh instance on the same file sees the entry.
            store2 = FingerprintStore(denylist_path=path)
            got = store2.is_denylisted(fp)
            self.assertIsNotNone(got)
            self.assertEqual(got["reason"], "stolen session")

    def test_denylist_reload_picks_up_file_edit(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "fingerprints_denylist.json")
            fp_a = self._fp("bad-a")
            fp_b = self._fp("bad-b")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "fingerprints": [
                    {"fingerprint": fp_a, "reason": "first"}]}, f)
            store = FingerprintStore(denylist_path=path)
            self.assertIsNotNone(store.is_denylisted(fp_a))
            self.assertIsNone(store.is_denylisted(fp_b))
            # Operator edits the file directly: replace the entry.
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "fingerprints": [
                    {"fingerprint": fp_b, "reason": "second"}]}, f)
            self.assertEqual(store.denylist_reload(), 1)
            self.assertIsNone(store.is_denylisted(fp_a))
            self.assertIsNotNone(store.is_denylisted(fp_b))

    def test_denylist_mtime_reload_on_lookup(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "fingerprints_denylist.json")
            fp_a = self._fp("bad-m1")
            fp_b = self._fp("bad-m2")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "fingerprints": [
                    {"fingerprint": fp_a, "reason": "first"}]}, f)
            store = FingerprintStore(denylist_path=path)
            self.assertIsNotNone(store.is_denylisted(fp_a))
            # Rewrite the file and force a clearly newer mtime.
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "fingerprints": [
                    {"fingerprint": fp_b, "reason": "second"}]}, f)
            os.utime(path, (2000000000, 2000000000))
            # No explicit reload: the lookup itself reloads on mtime.
            self.assertIsNotNone(store.is_denylisted(fp_b))
            self.assertIsNone(store.is_denylisted(fp_a))

    def test_denylist_invalid_file_entries_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "fingerprints_denylist.json")
            fp = self._fp("bad-ok")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "fingerprints": [
                    {"fingerprint": fp, "reason": "good"},
                    {"fingerprint": "not-a-hash", "reason": "bad"},
                    {"reason": "no fingerprint at all"},
                    "not-a-dict"]}, f)
            store = FingerprintStore(denylist_path=path)
            self.assertEqual(len(store.denylist_list()), 1)
            self.assertIsNotNone(store.is_denylisted(fp))

    def test_flag_does_not_denylist(self):
        # The no-automatic-denylisting rule, enforced: flagging a
        # fingerprint (the way screens learn) never puts it on the
        # denylist. Only an explicit operator add does.
        store = FingerprintStore()
        fp = self._fp("bad-flag")
        store.flag(fp, "ti_block:high")
        store.flag(fp, "kill_chain:flag")
        self.assertEqual(store.check(fp)["status"], "flagged")
        self.assertIsNone(store.is_denylisted(fp))

    def test_no_raw_pii_in_denylist_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "fingerprints_denylist.json")
            store = FingerprintStore(denylist_path=path)
            req = {"params": {"name": "check_link"},
                   "_rs_agent_id": "agent-secret-123"}
            out = fingerprint_for_request(
                req, _FakeHeaders(
                    {"User-Agent": "SecretAgent/9.9 (internal-build)"}),
                "203.0.113.77")
            store.denylist_add(out["fingerprint"], "stolen session")
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            self.assertNotIn("203.0.113.77", raw)
            self.assertNotIn("SecretAgent", raw)
            self.assertNotIn("agent-secret-123", raw)
            self.assertIn(out["fingerprint"], raw)

    def test_denylist_disabled_store_is_noop(self):
        store = FingerprintStore(enabled=False)
        fp = self._fp("bad-off")
        self.assertEqual(store.denylist_add(fp, "r"), {})
        self.assertIsNone(store.is_denylisted(fp))
        self.assertFalse(store.denylist_remove(fp))

    def test_summary_includes_denylist(self):
        store = FingerprintStore()
        fp = self._fp("bad-sum")
        store.observe(fp)
        store.denylist_add(fp, "r")
        summary = store.summary()
        self.assertEqual(summary["denylisted"], 1)
        self.assertEqual(summary["denylist"][0]["fingerprint"], fp)
        self.assertEqual(summary["total"], 1)


class TestDenylistOperatorToken(unittest.TestCase):
    """The Admin gate on denylist mutations.

    The proxy has no role system, so add/remove/reload are gated on
    the shared operator bearer token (MCP_PROXY_FINGERPRINT_
    DENYLIST_TOKEN). The console holds the token and only calls the
    proxy with it after checking the signed-in user's role (Admin or
    higher). These tests pin the fail-closed rule: an unconfigured
    token rejects every mutation rather than leaving the endpoints
    silently open.
    """
    _TOKEN = "op-token-abc123"

    def test_correct_token_accepted(self):
        self.assertTrue(denylist_token_ok(self._TOKEN, self._TOKEN))

    def test_wrong_token_rejected(self):
        self.assertFalse(denylist_token_ok("not-the-token",
                                           self._TOKEN))

    def test_token_is_case_sensitive(self):
        self.assertFalse(denylist_token_ok(self._TOKEN.upper(),
                                           self._TOKEN))

    def test_missing_provided_token_rejected(self):
        self.assertFalse(denylist_token_ok("", self._TOKEN))
        self.assertFalse(denylist_token_ok(None, self._TOKEN))

    def test_unconfigured_token_fails_closed(self):
        # No token configured on the proxy: every mutation is
        # rejected, even one carrying a plausible token. The gate
        # can never silently be absent.
        self.assertFalse(denylist_token_ok(self._TOKEN, ""))
        self.assertFalse(denylist_token_ok(self._TOKEN, None))
        self.assertFalse(denylist_token_ok("", ""))

    def test_token_never_leaks_into_summary(self):
        # The store never holds the token, so no read surface can
        # reveal it. (The token lives in config/env, not the store.)
        store = FingerprintStore()
        summary = store.summary()
        self.assertNotIn("token", summary)
        self.assertNotIn("denylist_token", summary)


if __name__ == "__main__":
    unittest.main()
