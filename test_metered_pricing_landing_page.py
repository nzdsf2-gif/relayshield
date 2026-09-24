"""Every entry in METERED_CREDIT_COSTS gets a price-card on
api.relayshield.net/developers, with three exceptions, each with its own
evidence read from the code rather than asserted:

    llm-credential-exposure  has its own dedicated licence section further
                             down the same page (id="llmjacking-license"),
                             so a second generic card would duplicate it.
    secret-scan-text        built for the rsscan pre-commit hook (its own
                             price comment: "$0.35 there would cost a [lot
                             for a hook firing on every commit]"), never
                             marketed to a general API buyer.
    wallet-risk             keyless and free at the bare /v1/wallet-risk
                             route; this metered variant exists only so the
                             MetaMask Snap can reach the same check with its
                             own API key (see the endpoint's own 2026-08-09
                             comment), so listing it as a $0.05 paid feature
                             would misdescribe the free route most callers use.

This closes the gap CLAUDE.md recorded twice by hand (incident-timeline,
then dependency-risk) with one guard that catches the NEXT one automatically,
rather than requiring someone to notice a third time. Reads the SERVED
price-grid HTML, never a claim that a card exists.
"""
import re
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent

# Each exception names the evidence for why it is excluded, not just that it
# is. A limit with no source is one the next session deletes.
EXCEPTIONS = {
    "/v1/metered/llm-credential-exposure": "has its own licence section, id=\"llmjacking-license\"",
    "/v1/metered/secret-scan-text":        "rsscan pre-commit hook price, not marketed generally",
    "/v1/metered/wallet-risk":             "free at bare /v1/wallet-risk; this is the Snap-only paid twin",
}


class EveryMeteredEndpointHasACard(unittest.TestCase):
    def setUp(self):
        api_src = (ROOT / "relayshield_api.py").read_text()
        m = re.search(r"METERED_CREDIT_COSTS: dict\[str, int\] = \{(.*?)\n\}", api_src, re.S)
        self.assertIsNotNone(m, "could not find METERED_CREDIT_COSTS in relayshield_api.py")
        self.costs = {path: int(cents) for path, cents in
                      re.findall(r'"(/v1/metered/[a-z0-9-]+)":\s*(\d+)', m.group(1))}
        self.assertGreater(len(self.costs), 0, "parsed zero entries -- the regex broke, not the data")

        self.page_src = (ROOT / "relayshield_developer_signup.py").read_text()
        # The "/ call" suffix is not universal -- bulk-ioc is billed
        # "/ batch (up to 100 IOCs)" -- so the match is on the price alone,
        # not on a specific unit label after it.
        self.cards = {}
        for path, price in re.findall(
                r'<div class="endpoint">(/v1/metered/[a-z0-9-]+)</div>\s*\n'
                r'\s*<div class="price">\$([\d.]+)<span class="per">',
                self.page_src):
            self.cards[path] = round(float(price) * 100)

    def test_every_exception_still_needs_to_be_one(self):
        """An exception that already has a card is stale bookkeeping, not a
        finding -- if it now has one, delete it from EXCEPTIONS rather than
        leaving a dead entry that hides the real check."""
        for path in EXCEPTIONS:
            self.assertNotIn(path, self.cards,
                              f"{path} is listed as an exception but already has a card -- "
                              f"remove it from EXCEPTIONS")

    def test_every_non_exception_metered_endpoint_has_a_matching_card(self):
        missing, mismatched = [], []
        for path, cents in self.costs.items():
            if path in EXCEPTIONS:
                continue
            if path not in self.cards:
                missing.append(path)
            elif self.cards[path] != cents:
                mismatched.append((path, cents, self.cards[path]))
        self.assertFalse(missing,
                          f"no price-card for: {missing} -- a metered endpoint with no card "
                          f"on api.relayshield.net/developers is live, charged, and invisible "
                          f"to anyone who is not already reading METERED_CREDIT_COSTS")
        self.assertFalse(mismatched,
                          f"landing page price disagrees with METERED_CREDIT_COSTS: {mismatched} "
                          f"-- copy shown to a buyer that disagrees with what we charge is a "
                          f"price we do not honour")

    def test_the_exceptions_list_does_not_silently_grow(self):
        """A future session adding a fourth exception without evidence is the
        CSM-SIMSWAP-1 shape: loosen the guard instead of fixing the gap. Caps
        the list at what is documented today; raise this number only alongside
        a comment naming the new exception's evidence."""
        self.assertLessEqual(len(EXCEPTIONS), 3,
                              "a new exception was added -- give it evidence in the module "
                              "docstring and EXCEPTIONS dict, the same way the other three have it")


if __name__ == "__main__":
    unittest.main()
