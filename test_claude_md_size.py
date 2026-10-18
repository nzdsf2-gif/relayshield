"""CLAUDE.md must stay small enough to be read, and splitting it must never lose a word.

CLAUDE.md reached 802,620 characters because every session appended to it, and Andrew's local
Claude Code reads only about 150,000. tools/claude_memory.py holds the caps, the index and the
rotation; this holds them to account. The real-repo test is the guard that fails the build when
a session appends its record to the wrong file; the temp-dir tests prove the tool's behaviour.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))
import claude_memory as cm  # noqa: E402


def make_root(claude="# C\n\n## Rule one\nbody\n", log_sections=(), volumes=()):
    root = tempfile.mkdtemp()
    mem = os.path.join(root, "docs", "claude_memory")
    os.makedirs(mem)
    cm.write(os.path.join(root, "CLAUDE.md"), claude)
    cm.write(os.path.join(mem, "LOG_CURRENT.md"),
             cm.LOG_HEADER + "\n".join(log_sections) + ("\n" if log_sections else ""))
    for i, secs in enumerate(volumes, 1):
        cm.write(os.path.join(mem, "archive_%02d.md" % i), cm.ARCHIVE_HEADER + "\n".join(secs) + "\n")
    cm.write(os.path.join(mem, "INDEX.md"), cm.build_index(root))
    return root


def section(name, size):
    return "## %s\n%s\n" % (name, "x" * size)


def all_text(root):
    mem = os.path.join(root, "docs", "claude_memory")
    out = []
    for f in ["LOG_CURRENT.md"] + cm.volumes(mem):
        out += [b for _, b in cm.split_sections(cm.read(os.path.join(mem, f)))[1]]
    return out


class TheRealRepo(unittest.TestCase):
    def test_sizes_and_index_are_within_their_caps(self):
        self.assertEqual(cm.check(), [], "run: python3 tools/claude_memory.py --check")

    def test_claude_md_is_under_the_limit_andrew_reported(self):
        self.assertLess(len(cm.read(cm.CLAUDE_MD)), 150_000)

    def test_the_caps_themselves_cannot_be_raised_past_the_limit(self):
        # The file is small today, so a raised cap would pass every other test until it mattered.
        self.assertLessEqual(cm.CLAUDE_MD_CAP, 130_000)
        self.assertLessEqual(cm.LOG_TARGET, cm.LOG_CAP)

    def test_the_organising_section_is_present_and_names_the_log(self):
        text = cm.read(cm.CLAUDE_MD)
        self.assertIn("## HOW THIS FILE IS ORGANISED", text)
        self.assertIn("docs/claude_memory/LOG_CURRENT.md", text)

    def test_the_guard_has_not_scoped_itself_down_to_nothing(self):
        idx = cm.read(cm.INDEX)
        self.assertGreaterEqual(len([x for x in idx.split("\n") if ":" in x and not x.startswith("#")]), 200)
        self.assertGreaterEqual(len(cm.volumes()), 5)

    def test_a_standing_rule_is_still_in_the_file_sessions_load(self):
        # If the split ever moves these out, a session reading only CLAUDE.md loses its rules.
        text = cm.read(cm.CLAUDE_MD)
        for must in ("HOW TO DELIVER WORK TO ANDREW", "EVERY COMMAND BLOCK STARTS WITH THE MERGE",
                     "COMMANDS HANDED TO ANDREW", "THE DRIFT RULE", "MEASUREMENT DOCTRINE",
                     "THE API LANDING PAGE IS"):
            self.assertIn("## " + must, text)


class SplitSections(unittest.TestCase):
    def test_round_trips_exactly(self):
        for text in ("# T\n\n## A\nx\n\n## B\ny\n", "no headings at all\n", "## only\n",
                     "# T\n\n## A\n```zsh\nunbalanced fence\n\n## B\n### sub\nz\n"):
            pre, secs = cm.split_sections(text)
            self.assertEqual(cm.join_sections(pre, secs), text)

    def test_a_third_level_heading_does_not_split(self):
        _, secs = cm.split_sections("## A\n### inner\nbody\n## B\n")
        self.assertEqual([h for h, _ in secs], ["A", "B"])

    def test_an_unbalanced_fence_does_not_swallow_later_headings(self):
        # The real CLAUDE.md has these; a fence-aware parser lost every heading after one.
        _, secs = cm.split_sections("## A\n```zsh\nnever closed\n## B\n## C\n")
        self.assertEqual([h for h, _ in secs], ["A", "B", "C"])


class Check(unittest.TestCase):
    def tearDown(self):
        for r in getattr(self, "roots", []):
            shutil.rmtree(r, ignore_errors=True)

    def root(self, **kw):
        self.roots = getattr(self, "roots", []) + [make_root(**kw)]
        return self.roots[-1]

    def test_a_clean_tree_has_no_problems(self):
        self.assertEqual(cm.check(self.root()), [])

    def test_an_oversized_claude_md_is_reported(self):
        r = self.root(claude="# C\n\n" + section("Big", cm.CLAUDE_MD_CAP + 1))
        self.assertTrue(any("CLAUDE.md is" in p for p in cm.check(r)))

    def test_an_oversized_log_is_reported(self):
        r = self.root(log_sections=[section("Big", cm.LOG_CAP + 1)])
        self.assertTrue(any("LOG_CURRENT.md is" in p for p in cm.check(r)))

    def test_a_stale_index_is_reported(self):
        r = self.root()
        cm.write(os.path.join(r, "CLAUDE.md"), "# C\n\n## Rule one\nbody\n\n## A rule added later\nbody\n")
        self.assertTrue(any("INDEX.md" in p for p in cm.check(r)))

    def test_the_index_names_file_and_line(self):
        r = self.root(log_sections=["## Recent\nx\n"], volumes=[["## Old\ny\n"]])
        idx = cm.build_index(r)
        self.assertIn("CLAUDE.md:3  Rule one", idx)
        self.assertIn("archive_01.md:", idx)
        self.assertIn("  Old", idx)


class Rotate(unittest.TestCase):
    def setUp(self):
        self.sizes = 25_000
        self.log = [section("L%d" % i, self.sizes) for i in range(5)]      # ~125k, over the target
        self.root = make_root(log_sections=self.log, volumes=[[section("OLD", 1000)]])
        self.before = all_text(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_a_dry_run_writes_nothing(self):
        moved = cm.rotate(self.root, do_write=False)
        self.assertTrue(moved)
        self.assertEqual(all_text(self.root), self.before)

    def test_rotation_is_lossless_and_keeps_order(self):
        moved = cm.rotate(self.root, do_write=True)
        self.assertEqual(moved[0], "L0")
        after = all_text(self.root)
        self.assertEqual(sorted(x.rstrip("\n") for x in after), sorted(x.rstrip("\n") for x in self.before))
        mem = os.path.join(self.root, "docs", "claude_memory")
        flat = []
        for f in cm.volumes(mem):
            flat += [h for h, _ in cm.split_sections(cm.read(os.path.join(mem, f)))[1]]
        flat += [h for h, _ in cm.split_sections(cm.read(os.path.join(mem, "LOG_CURRENT.md")))[1]]
        self.assertEqual(flat, ["OLD", "L0", "L1", "L2", "L3", "L4"], "oldest first, newest last")

    def test_the_log_ends_under_its_target_and_the_index_is_refreshed(self):
        cm.rotate(self.root, do_write=True)
        mem = os.path.join(self.root, "docs", "claude_memory")
        self.assertLessEqual(len(cm.read(os.path.join(mem, "LOG_CURRENT.md"))), cm.LOG_TARGET + self.sizes)
        self.assertEqual(cm.check(self.root), [])

    def test_the_newest_section_is_never_rotated_out(self):
        r = make_root(log_sections=[section("Only", cm.LOG_TARGET * 2)])
        try:
            self.assertEqual(cm.rotate(r, do_write=True), [])
            self.assertIn("Only", cm.read(os.path.join(r, "docs", "claude_memory", "LOG_CURRENT.md")))
        finally:
            shutil.rmtree(r, ignore_errors=True)

    def test_a_full_volume_starts_a_new_one(self):
        r = make_root(log_sections=self.log, volumes=[[section("FULL", cm.VOLUME_CAP - 500)]])
        try:
            cm.rotate(r, do_write=True)
            mem = os.path.join(r, "docs", "claude_memory")
            self.assertEqual(cm.volumes(mem), ["archive_01.md", "archive_02.md"])
            self.assertTrue(cm.read(os.path.join(mem, "archive_02.md")).startswith(cm.ARCHIVE_HEADER))
        finally:
            shutil.rmtree(r, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
