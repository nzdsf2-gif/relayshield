"""The number rsscan tells a user is the number rsscan has.

WHY THIS EXISTS. `rsscan/README.md` and the module docstring in
`rsscan/rsscan/scan.py` both stated "31 credential patterns" while the table
held 49, because eight GitLab formats were added on 2026-09-16 and neither
sentence moved. Nothing errored. A user installing the package read a number
that was eighteen short, next to a provider list that named GitHub and not
GitLab -- in the same week we published a post whose whole argument is that a
detector reports only what it has a pattern for.

This is the two-files-must-agree shape this repo has now paid for five times,
and the answer is the same every time: derive the number, or check it.
PATTERN_COUNT is already derived (`len(_COMPILED)`), so the prose is the only
thing that can drift and it is what this file pins.

STRIPPING COMMENTS IS NOT THE ANSWER HERE, and that is worth stating because
every other guard in this repo does it. The thing being checked IS prose: the
README line and the docstring are what a user reads. Scanning the code half
would prove nothing about either.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "rsscan"))

from rsscan.patterns import NHI_PATTERNS, PATTERN_COUNT  # noqa: E402

STATED = re.compile(r"(\d+) credential patterns")


class TestStatedCountMatchesTheTable(unittest.TestCase):

    def test_pattern_count_is_derived_not_typed(self):
        self.assertEqual(PATTERN_COUNT, len(NHI_PATTERNS),
                         "PATTERN_COUNT must be len() of the table, never a literal")

    def test_every_stated_count_matches(self):
        checked = 0
        for rel in ("rsscan/README.md", "rsscan/rsscan/scan.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for m in STATED.finditer(text):
                checked += 1
                line = text[:m.start()].count("\n") + 1
                self.assertEqual(
                    int(m.group(1)), PATTERN_COUNT,
                    f"{rel}:{line} says {m.group(1)} credential patterns, "
                    f"the table holds {PATTERN_COUNT}")
        self.assertGreater(checked, 0,
                           "no stated count found at all -- this guard has "
                           "scoped itself down to nothing, which passes forever")


class TestTheProviderListNamesWhatWeDetect(unittest.TestCase):
    """A provider named in the table and absent from the README reads, to a
    reader who checks, as the product overselling. GitLab is the live case:
    eight formats shipped and the README still said GitHub only."""

    README = (ROOT / "rsscan" / "README.md").read_text(encoding="utf-8")

    def detection_sentence(self):
        """The line that lists what rsscan DETECTS, not the whole README.

        The first version of this test searched the whole file for "gitlab"
        and passed with the provider clause deleted, because the README also
        documents a GitLab CI component -- so the word is present whatever the
        pattern table holds. A guard that cannot fail is decoration, and this
        one was, on its first proof run."""
        for line in self.README.splitlines():
            if "credential patterns" in line:
                return line.lower()
        self.fail("no sentence naming the detected providers")

    def test_gitlab_is_named_where_providers_are_listed(self):
        self.assertIn("gitlab", self.detection_sentence(),
                      "the table carries GitLab token formats; the sentence a "
                      "new installer reads about what rsscan detects must "
                      "name them, and a GitLab CI integration elsewhere in the "
                      "README is not that sentence")

    def test_the_table_actually_carries_gitlab(self):
        # The assertion above is only meaningful while this holds. A README
        # naming a provider we do not detect is the worse of the two failures.
        names = [t[0] for t in NHI_PATTERNS]
        self.assertTrue(any(n.startswith("gitlab_") for n in names),
                        "README names GitLab but no gitlab_* rule exists")


class TestTheReadmeSeverityTableMatchesTheRules(unittest.TestCase):
    """The README now prints a prefix/severity table, which is a THIRD place
    the same facts live. Two places that must agree with nothing checking them
    is this repo's most repeated defect; three is worse, and a README is the
    copy a user acts on when deciding whether a finding is urgent."""

    README = (ROOT / "rsscan" / "README.md").read_text(encoding="utf-8")
    ROW = re.compile(r"^\|\s*`(gl[a-z]*-)`\s*\|[^|]*\|\s*(CRITICAL|HIGH)\s*\|", re.M)

    def rules_by_prefix(self):
        out = {}
        for entry in NHI_PATTERNS:
            name, pattern, severity = entry[0], entry[1], entry[2]
            if not name.startswith("gitlab_"):
                continue
            m = re.search(r"(gl[a-z]*-)", pattern)
            if m:
                out.setdefault(m.group(1), set()).add(severity)
        return out

    def test_every_documented_prefix_exists_and_agrees(self):
        rows = self.ROW.findall(self.README)
        self.assertTrue(rows, "no GitLab severity table found in the README")
        rules = self.rules_by_prefix()
        for prefix, severity in rows:
            with self.subTest(prefix=prefix):
                self.assertIn(prefix, rules,
                              f"README documents {prefix} but no rule matches it")
                self.assertEqual(
                    rules[prefix], {severity},
                    f"README says {prefix} is {severity}, the rules say "
                    f"{sorted(rules[prefix])}")

    def test_every_rule_prefix_is_documented(self):
        # The other direction, which is the one that silently drifts: a rule
        # shipped and never written down is coverage the user cannot know
        # they have.
        documented = {p for p, _ in self.ROW.findall(self.README)}
        for prefix in self.rules_by_prefix():
            self.assertIn(prefix, documented,
                          f"rule prefix {prefix} is not in the README table")


if __name__ == "__main__":
    unittest.main(verbosity=2)
