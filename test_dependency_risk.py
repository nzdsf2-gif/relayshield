"""/v1/metered/dependency-risk was registered in METERED_CREDIT_COSTS and the
dispatch table since 2026-08-12 but had no card on api.relayshield.net/developers
-- CLAUDE.md flagged this as "missing from the price-grid with no visible
justification" while fixing the identical gap for /v1/metered/incident-timeline.
Same guard, same shape: read the SERVED price-grid HTML, not a claim it exists.
"""
import re
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


class LandingPagePriceCard(unittest.TestCase):
    def setUp(self):
        api_src = (ROOT / "relayshield_api.py").read_text()
        m = re.search(r'"/v1/metered/dependency-risk":\s*(\d+),', api_src)
        self.assertIsNotNone(m, "dependency-risk missing from METERED_CREDIT_COSTS")
        self.credit_cost_cents = int(m.group(1))
        self.page_src = (ROOT / "relayshield_developer_signup.py").read_text()

    def test_it_has_a_price_card_on_the_landing_page(self):
        m = re.search(
            r'<div class="endpoint">/v1/metered/dependency-risk</div>\s*\n'
            r'\s*<div class="price">\$([\d.]+)<span class="per"> / call</span></div>',
            self.page_src)
        self.assertIsNotNone(m, "no price-card found for /v1/metered/dependency-risk "
                              "on the api.relayshield.net/developers price grid")
        cents_on_page = round(float(m.group(1)) * 100)
        self.assertEqual(cents_on_page, self.credit_cost_cents,
                          "the landing page quotes a different price than METERED_CREDIT_COSTS "
                          "-- copy shown to a buyer that disagrees with what we charge is a "
                          "price we do not honour")

    def test_it_is_also_in_the_quickstart_email(self):
        self.assertIn("/v1/metered/dependency-risk", self.page_src.split("Quick start")[0])


if __name__ == "__main__":
    unittest.main()
