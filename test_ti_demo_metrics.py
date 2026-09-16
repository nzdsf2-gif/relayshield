#!/usr/bin/env python3
"""Guards on the TI demo's four stat cards, read from the SERVED page.

THE DEFECT THESE EXIST FOR IS A UNIT, NOT A DATE. Until 2026-09-16 the first
card read "5.4M+ / IOC indicators" over the ROW COUNT of relayshield_intel_iocs.
That table is keyed (ioc_value, seen_ts), so a value seen on five days is five
rows, and export_intel_sample.py's own collapse() docstring says what follows:
"Counting rows would inflate every number we quote." The last measured split was
494K distinct against 5.8M sightings. So the card overstated by roughly an order
of magnitude against the word printed beneath it, on the page most likely to be
opened by somebody who checks -- which is the audience MEASUREMENT DOCTRINE was
written about.

Refreshing the figure would have kept the defect and changed its date. A guard
is the only thing that stops the next refresh doing exactly that.

READ FROM THE SERVED BYTES, never the source. The page lives in a template
literal, and this repo has shipped a dead Worker three times on the gap between
what the file says and what a browser receives.
"""

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKER = ROOT / "cloudflare_worker_ti_demo.js"

# The word that makes the label honest. "Indicator sightings" is correct and
# "IOC indicators" is the defect, so the rule cannot be a banned-word list --
# the first version of this guard was exactly that and it FAILED ON THE CORRECT
# LABEL, which is the shape that gets a check loosened rather than obeyed. The
# real rule is narrower: a label may name indicators, and if it does it must
# also name the unit.
UNIT_WORD = "sighting"
INDICATOR_WORDS = ("indicator", "ioc")


def served_page() -> str:
    """Execute the Worker and return the HTML a browser actually gets."""
    out = subprocess.run(
        ["node", str(ROOT / "tools" / "ti_demo_render.mjs")],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise AssertionError(
            "the TI demo Worker did not serve a page. That is a RUNTIME "
            "failure `node --check` cannot see:\n" + out.stderr)
    return out.stdout


def cards(html: str):
    """[(number, label)] for each stat card, in order."""
    return re.findall(
        r'<div class="stat-num">([^<]*)</div><div class="stat-label">([^<]*)</div>',
        html)


class TestTheCardsAreServedAtAll(unittest.TestCase):
    def setUp(self):
        self.html = served_page()

    def test_four_cards_render(self):
        self.assertEqual(len(cards(self.html)), 4, "expected four stat cards")


class TestTheRowCountIsNeverLabelledIndicators(unittest.TestCase):
    """The defect itself: a sightings number under an indicators label."""

    def setUp(self):
        self.cards = cards(served_page())

    def test_the_corpus_card_says_sightings(self):
        num, label = self.cards[0]
        low = label.lower()
        self.assertIn(
            UNIT_WORD, low,
            "the first card is the relayshield_intel_iocs ROW COUNT. It is a "
            "sightings figure and the label has to say so: " + label)

    def test_naming_indicators_without_the_unit_is_the_old_defect(self):
        """"IOC indicators" over a row count is what shipped for a month."""
        for num, label in self.cards:
            low = label.lower()
            if any(w in low for w in INDICATOR_WORDS):
                with self.subTest(label=label):
                    self.assertIn(
                        UNIT_WORD, low,
                        "a card naming indicators over the intel_iocs row "
                        "count must say 'sightings'. A distinct-indicator "
                        "count needs ti_demo_metrics.py --distinct, which is a "
                        "full multi-million-row scan: " + label)

    def test_the_corpus_card_is_a_floor_not_a_precise_figure(self):
        """An approximate number is never printed as though it were exact.

        DescribeTable's ItemCount is refreshed roughly every six hours, so it is
        honest as '7.6M+' and dishonest as '7,602,575' -- and the second form
        invites somebody to check it against a number that has since moved.
        """
        num = self.cards[0][0]
        self.assertTrue(
            num.rstrip().endswith("+"),
            "the corpus figure comes from an approximate ItemCount, so it is "
            "written as a floor: " + num)

    def test_the_hero_agrees_with_the_card(self):
        """Two numbers on one page that disagree is the defect one layer over."""
        html = served_page()
        hero = re.search(r"<p>Query ([^<]*)</p>", html)
        self.assertIsNotNone(hero, "the hero paragraph is gone")
        text = hero.group(1).lower()
        self.assertIn(
            "sighting", text,
            "the hero quotes the same corpus figure as card one and must carry "
            "the same unit: " + hero.group(1))


class TestTheSmallCountsAreExact(unittest.TestCase):
    """Channels, families and MITRE groups are small and directly counted.

    These come from a real scan rather than ItemCount, so they are printed
    exactly -- and a '+' on them would be hiding precision we actually have.
    """

    def setUp(self):
        self.cards = cards(served_page())

    def test_they_carry_no_plus(self):
        for num, label in self.cards[1:]:
            with self.subTest(label=label):
                self.assertFalse(
                    num.strip().endswith("+"),
                    "%s is counted exactly; a '+' implies an estimate: %s"
                    % (label, num))


class TestTheMeasurementRouteIsRecorded(unittest.TestCase):
    """The comment must name the tool, or the next refresh is done by hand.

    Editing these by hand is how a row count got an indicators label in the
    first place: the number came from a query somebody ran once and the unit
    came from whatever the card already said.
    """

    def test_the_source_comment_names_the_tool(self):
        src = WORKER.read_text(encoding="utf-8")
        self.assertIn(
            "tools/ti_demo_metrics.py", src,
            "the stat-card comment must name the tool that measures them")


if __name__ == "__main__":
    unittest.main(verbosity=1)
