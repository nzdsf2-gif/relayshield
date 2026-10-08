"""Unit tests for the Phase 4 audit trail."""

import os
import tempfile
import unittest

from .audit import AuditTrail


class TestAuditTrail(unittest.TestCase):
    def test_record_and_count(self):
        a = AuditTrail()
        a.record("agent-1", "http://s:9000", "read_file",
                 {"path": "/tmp/x"}, "allow", "clean")
        a.record("agent-1", "http://s:9000", "exec_shell",
                 {"cmd": "rm -rf /"}, "block", "policy_deny",
                 reasons=["denied by policy"])
        self.assertEqual(a.count(), 2)

    def test_args_never_stored_raw(self):
        a = AuditTrail()
        entry = a.record("a", "s", "t", {"secret": "hunter2"},
                         "allow", "clean")
        self.assertNotIn("hunter2", str(entry))
        self.assertIn("args_hash", entry)

    def test_chain_verifies(self):
        a = AuditTrail()
        for i in range(5):
            a.record("a", "s", f"tool_{i}", {}, "allow", "clean")
        result = a.verify_chain()
        self.assertTrue(result["ok"])
        self.assertEqual(result["checked"], 5)

    def test_chain_detects_tamper(self):
        a = AuditTrail()
        a.record("a", "s", "t", {}, "allow", "clean")
        a.record("a", "s", "t", {}, "block", "prompt_injection")
        # Tamper with the first entry's decision.
        a._entries[0]["decision"] = "allow-evil"
        result = a.verify_chain()
        self.assertFalse(result["ok"])

    def test_genesis_prev_hash(self):
        a = AuditTrail()
        entry = a.record("a", "s", "t", {}, "allow", "clean")
        self.assertEqual(entry["prev_hash"], "GENESIS")

    def test_chained_prev_hash(self):
        a = AuditTrail()
        first = a.record("a", "s", "t", {}, "allow", "clean")
        second = a.record("a", "s", "t", {}, "allow", "clean")
        self.assertEqual(second["prev_hash"], first["entry_hash"])

    def test_export_json(self):
        a = AuditTrail()
        a.record("a", "s", "t", {}, "allow", "clean")
        data = a.export_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["tool"], "t")

    def test_export_csv(self):
        a = AuditTrail()
        a.record("a", "s", "t", {}, "block", "kit_match")
        csv_text = a.export_csv()
        self.assertIn("seq,ts,agent", csv_text)
        self.assertIn("kit_match", csv_text)

    def test_persist_and_reload(self):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        try:
            a = AuditTrail(persist_path=path)
            a.record("a", "s", "t", {}, "allow", "clean")
            b = AuditTrail(persist_path=path)
            self.assertEqual(b.count(), 1)
            self.assertTrue(b.verify_chain()["ok"])
        finally:
            os.unlink(path)

    def test_summary(self):
        a = AuditTrail()
        a.record("a", "s", "t", {}, "allow", "clean")
        a.record("a", "s", "t", {}, "block", "pii_leak")
        s = a.summary()
        self.assertEqual(s["entries"], 2)
        self.assertEqual(s["decisions"]["block"], 1)
        self.assertTrue(s["chain_ok"])


if __name__ == "__main__":
    unittest.main()
