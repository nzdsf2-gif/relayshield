"""The privacy policy's MCP proxy section must say what the code actually does."""
import re
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
SRC = (ROOT / "cloudflare_worker_privacy.js").read_text(encoding="utf-8")
API = (ROOT / "relayshield_api.py").read_text(encoding="utf-8")


def section(n):
    m = re.search(rf"<h2>{n}\. [^<]+</h2>(.*?)(?=<h2>|<hr>)", SRC, re.S)
    return m.group(1) if m else ""


class Policy(unittest.TestCase):
    def test_headings_are_numbered_consecutively(self):
        nums = [int(n) for n in re.findall(r"<h2>(\d+)\. ", SRC)]
        self.assertEqual(nums, list(range(1, len(nums) + 1)))

    def test_the_contact_reference_points_at_the_contact_section(self):
        m = re.search(r"address in section (\d+)", SRC)
        self.assertIsNotNone(m)
        self.assertRegex(SRC, rf"<h2>{m.group(1)}\. Contact</h2>")

    def test_the_proxy_is_named_in_the_intro(self):
        self.assertIn("RelayShield MCP proxy", SRC.split("<h2>")[0])

    def test_it_discloses_that_the_server_address_is_screened(self):
        # NeighborRegistry.register() sends each upstream server's domain to the
        # screening API on first sight. The policy must not claim otherwise.
        self.assertIn("the address of each MCP server it connects to", section(12))
        src = (ROOT / "mcp_proxy" / "neighbor.py").read_text()
        self.assertIn("TI-screen its domain", src)

    def test_it_says_off_by_default(self):
        self.assertIn("off by default", section(12))

    def test_it_discloses_both_levels_and_the_key_requirement(self):
        t = section(12)
        self.assertIn("Counts.", t)
        self.assertIn("Indicators.", t)
        self.assertIn("requires your RelayShield API key", t)

    def test_it_lists_what_is_never_sent(self):
        t = section(12)
        for must in ("Tool arguments", "tool names", "agent identities", "client IP addresses",
                     "private, internal or local hostname"):
            self.assertIn(must, t)

    def test_it_promises_no_corpus_promotion_without_confirmation(self):
        self.assertIn("unless we have independently confirmed it", section(12))

    def test_stated_retention_matches_the_code(self):
        t = section(12)
        body = re.search(r"def handle_mcp_proxy_telemetry\(.*?(?=\n\n\nROUTES)", API, re.S).group(0)
        self.assertIn("180 * 86400", body)
        self.assertIn("365 * 86400", body)
        self.assertIn("180 days", t)
        self.assertIn("365 days", t)

    def test_no_data_vendor_is_named_and_no_em_dash(self):
        t = section(12).lower()
        for banned in ("have i been pwned", "hudson rock", "hibp", "twilio"):
            self.assertNotIn(banned, t)
        self.assertNotIn("—", SRC)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_the_worker_parses(self):
        r = subprocess.run(["node", "--check", str(ROOT / "cloudflare_worker_privacy.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
