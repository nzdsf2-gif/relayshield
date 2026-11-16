"""tools/intel_keyword_yield.py -- the sweep keyword lists it reports on (2026-11-16).

The tool keeps the sweeps (001, 001b, 002, 003) as explicit lists, copied from
intel_channel_recommendations.md, and reads SEARCH_KEYWORDS by AST. These pin
that the two cannot silently drift: a keyword retired from SEARCH_KEYWORDS
without updating SWEEPS (or the reverse) fails here, not on the founder's Mac.
No AWS and no boto3 needed: the tool imports boto3 only inside main().
"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import intel_keyword_yield as m  # noqa: E402


class SweepLists(unittest.TestCase):
    def setUp(self):
        self.live = m.keywords_from_source(
            (ROOT / "relayshield_intel_discovery.py").read_text(encoding="utf-8"))

    def test_every_sweep_keyword_is_live(self):
        missing = [k for k in m.all_sweep_keywords() if k not in self.live]
        self.assertEqual(missing, [], "retired from SEARCH_KEYWORDS: update SWEEPS "
                         "and record the retirement in intel_channel_recommendations.md")

    def test_counts_match_the_record(self):
        self.assertEqual({s: len(v) for s, v in m.SWEEPS.items()},
                         {"001": 10, "001b": 4, "002": 13, "003": 16})

    def test_ast_reader_handles_the_real_list(self):
        self.assertGreater(len(self.live), 100)
        self.assertEqual(len(self.live), len(set(self.live)), "duplicate keyword")


if __name__ == "__main__":
    unittest.main()
