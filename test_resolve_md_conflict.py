"""Tests for tools/resolve_md_conflict.py.

The near-duplicate test is the one that matters. The first version of
duplicate_headings() compared headings for EXACT equality, so it sailed straight
past "THE TOP 15, REGENERATED 2026-09-08" against "... 2026-09-09" -- the only
collision this repo has actually had. Caught by running it against that real
pair rather than against a fixture written to match the assumption.
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import resolve_md_conflict as r  # noqa: E402


def L(text):
    return text.splitlines(keepends=True)


class TestResolve(unittest.TestCase):
    def test_keeps_both_sides_and_drops_markers(self):
        lines = L("# D\n<<<<<<< HEAD\nOURS\n=======\nTHEIRS\n>>>>>>> branch\ntail\n")
        out, n = r.resolve(lines)
        self.assertEqual(n, 1)
        joined = "".join(out)
        self.assertIn("OURS", joined)
        self.assertIn("THEIRS", joined)
        for marker in ("<<<<<<<", "=======", ">>>>>>>"):
            self.assertNotIn(marker, joined)

    def test_ours_comes_before_theirs(self):
        out, _ = r.resolve(L("<<<<<<< HEAD\nA\n=======\nB\n>>>>>>> x\n"))
        joined = "".join(out)
        self.assertLess(joined.index("A"), joined.index("B"))

    def test_multiple_conflicts(self):
        out, n = r.resolve(L(
            "<<<<<<< HEAD\nA\n=======\nB\n>>>>>>> x\n"
            "mid\n"
            "<<<<<<< HEAD\nC\n=======\nD\n>>>>>>> x\n"))
        self.assertEqual(n, 2)
        for want in ("A", "B", "C", "D", "mid"):
            self.assertIn(want, "".join(out))

    def test_unterminated_conflict_refuses(self):
        with self.assertRaises(SystemExit):
            r.resolve(L("<<<<<<< HEAD\nA\n"))
        with self.assertRaises(SystemExit):
            r.resolve(L("<<<<<<< HEAD\nA\n=======\nB\n"))

    def test_nested_marker_refuses(self):
        with self.assertRaises(SystemExit):
            r.resolve(L("<<<<<<< HEAD\n<<<<<<< HEAD\nA\n=======\nB\n>>>>>>> x\n"))


class TestDuplicateHeadings(unittest.TestCase):
    def test_flags_headings_differing_only_by_date(self):
        # THE case. Not equal strings, and the reason the first version was wrong.
        dupes = r.duplicate_headings(L(
            "### THE TOP 15, REGENERATED 2026-09-09\nx\n"
            "### THE TOP 15, REGENERATED 2026-09-08\ny\n"))
        self.assertEqual(len(dupes), 1)
        self.assertFalse(dupes[0][4], "should be reported as a near-duplicate, not exact")

    def test_flags_identical_headings(self):
        dupes = r.duplicate_headings(L("## SAME\nx\n## SAME\ny\n"))
        self.assertEqual(len(dupes), 1)
        self.assertTrue(dupes[0][4], "should be reported as exact")

    def test_distinct_headings_are_not_flagged(self):
        self.assertEqual(r.duplicate_headings(L("## ALPHA\nx\n## BETA\ny\n")), [])

    def test_body_text_is_not_a_heading(self):
        self.assertEqual(r.duplicate_headings(L("not # a heading\n#no space\n")), [])


class TestCli(unittest.TestCase):
    def _run(self, text, *args):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "CLAUDE.md"
            f.write_text(text)
            out = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "resolve_md_conflict.py"),
                 str(f), *args],
                capture_output=True, text=True, timeout=60)
            return out, f.read_text()

    def test_no_markers_is_a_noop(self):
        out, after = self._run("# clean\n")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("no conflict markers", out.stdout)
        self.assertEqual(after, "# clean\n")

    def test_dry_run_does_not_write(self):
        src = "<<<<<<< HEAD\nA\n=======\nB\n>>>>>>> x\n"
        out, after = self._run(src)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Dry run", out.stdout)
        self.assertEqual(after, src, "dry run must not modify the file")

    def test_write_applies(self):
        out, after = self._run("<<<<<<< HEAD\nA\n=======\nB\n>>>>>>> x\n", "--write")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("A", after)
        self.assertIn("B", after)
        self.assertNotIn("<<<<<<<", after)


if __name__ == "__main__":
    unittest.main()
