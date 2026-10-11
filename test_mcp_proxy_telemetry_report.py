import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("r", ROOT / "tools" / "mcp_proxy_telemetry_report.py")
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)

ITEMS = [
    {"pk": "INSTALL#a", "sk": "REPORT#2026-10-12T00:00:00+00:00",
     "counts": [{"category": "pii_leak", "taxonomy_id": "", "kind": "call", "n": 4}]},
    {"pk": "INSTALL#b", "sk": "REPORT#2026-10-12T01:00:00+00:00",
     "counts": [{"category": "pii_leak", "taxonomy_id": "", "kind": "call", "n": 1}]},
    {"pk": "INSTALL#a", "sk": "REPORT#2020-01-01T00:00:00+00:00",
     "counts": [{"category": "pii_leak", "taxonomy_id": "", "kind": "call", "n": 99}]},
    {"pk": "RATE#a", "sk": "2026-10-12T00", "n": 5},
    {"pk": "CAND#x", "sk": "CAND", "last_seen": "2026-10-12", "reporters": {"r1", "r2"}, "report_count": 3,
     "host": "h.example.org", "payload_hash": "a" * 64, "category": "prompt_injection"},
    {"pk": "CAND#y", "sk": "CAND", "last_seen": "2026-10-12", "reporters": {"r1"}, "report_count": 9,
     "host": "z.example.org", "payload_hash": "b" * 64, "category": "pii_leak"},
]


class Report(unittest.TestCase):
    def test_window_and_distinct_installs(self):
        s = m.summarise(ITEMS, "2026-10-01", 1)
        self.assertEqual(s["installs"], 2)
        self.assertEqual(s["counts"][("pii_leak", "", "call")], 5)  # the 2020 row is outside the window

    def test_rate_rows_are_not_counted(self):
        self.assertEqual(m.summarise(ITEMS, "2026-10-01", 1)["installs"], 2)

    def test_distinct_reporters_beat_report_volume(self):
        s = m.summarise(ITEMS, "2026-10-01", 1)
        self.assertEqual([c["host"] for c in s["candidates"]], ["h.example.org", "z.example.org"])
        s2 = m.summarise(ITEMS, "2026-10-01", 2)
        self.assertEqual([c["host"] for c in s2["candidates"]], ["h.example.org"])

    def test_read_only(self):
        src = (ROOT / "tools" / "mcp_proxy_telemetry_report.py").read_text()
        for banned in (".put_item(", ".update_item(", ".delete_item(", ".batch_writer("):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()
