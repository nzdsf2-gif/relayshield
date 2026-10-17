"""Runs shopify/test_worker_session.mjs under node. Skipped if node is absent."""
import shutil, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ShopifyWorker(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_worker_session_flow(self):
        r = subprocess.run(["node", str(ROOT / "shopify" / "test_worker_session.mjs")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("5 passed", r.stdout)


if __name__ == "__main__":
    unittest.main()
