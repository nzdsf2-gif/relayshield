#!/usr/bin/env python3
"""CSM-SIMSWAP-1: the app must not sell SIM swap monitoring until it enrols.

THE DEFECT. Crypto Shield Mobile collected the phone number, labelled it "Used
for SIM swap monitoring", sold "SIM swap monitoring" on the paywall, claimed
"SIM-swap and breach exposure alerts" in the Solana dApp Store listing, told
every new user in onboarding step 3 to enter their number "to enable
monitoring", and shipped the SIM_SWAP alert card and the full carrier-by-carrier
remediation guide.

`checkSimSwap()` in src/api/relayshield.ts has ZERO CALLERS. The number is
written to SecureStore and read by nothing, so scan_sim_swap_users() -- which
filters on sim_swap_monitoring == True -- has never had a Crypto Shield Mobile
user in its set.

AND IT WAS FOUND ON 2026-08-14 AND WRITTEN DOWN IN THE FILE BUILT TO FIX IT.
relayshield_sim_swap_consent.py's docstring says so verbatim. That audit found
four defects, one per surface; the Telegram, WhatsApp and Stripe halves were
wired and this one was recorded and left. A finding with no guard is a finding
that comes back.

THE RULE THIS PINS, AND IT IS DELIBERATELY REVERSIBLE: the claim may return the
moment the app actually enrols. The test keys on the CALL, not on a date or a
flag, so shipping the feature unblocks the copy automatically and nobody has to
remember why the wording is cautious.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "crypto-shield-app"

ENROLL_ENDPOINT = "/v1/sim-swap/enroll"


def code_only(text: str) -> str:
    """Strip // line comments, /* */ blocks and {/* */} JSX comments.

    SIXTH TIME IN THIS REPO, so it is the FIRST version of this guard that does
    it rather than the second. Every file below now carries a comment explaining
    the removed claim, and every one of those comments quotes the claim.
    """
    text = re.sub(r"\{\s*/\*.*?\*/\s*\}", " ", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    return text


def app_enrols() -> bool:
    """Does any app source actually POST the enrolment endpoint?"""
    for path in APP.joinpath("src").rglob("*.ts*"):
        if ENROLL_ENDPOINT in code_only(path.read_text()):
            return True
    return False


# THE ONE LEGITIMATE EXEMPTION, AND IT IS NARROW ON PURPOSE.
#
# The onboarding screen's last step lists OTHER RelayShield products, and the
# Developer API card says the API does "SIM swap monitoring". That is TRUE:
# /v1/metered/sim-swap is live, priced, Twilio-approved for the US, and sold on
# the PAYG and AWS rails. The app is what does not enrol anyone.
#
# So the guard would otherwise force us to delete an accurate sentence about a
# real product to describe a different product honestly, which is the shape of
# a check that gets loosened rather than obeyed. It exempts lines that are
# plainly about another RelayShield surface and nothing else -- narrow enough
# that a feature bullet about THIS app can never hide behind it, because a
# feature bullet does not carry a relayshield.net URL or the words "REST API".
_OTHER_PRODUCT = ("relayshield.net", "REST API", "Developer API")


def _about_another_product(line: str) -> bool:
    return any(marker in line for marker in _OTHER_PRODUCT)


SURFACES = [
    APP / "src" / "components" / "PaywallModal.tsx",
    APP / "src" / "screens" / "PaywallScreen.tsx",
    APP / "src" / "screens" / "SettingsScreen.tsx",
    APP / "src" / "screens" / "OnboardingScreen.tsx",
    APP / "store-assets" / "dapp-store-metadata.md",
]

# Phrases that promise the app DOES it. "SIM swap" as a threat noun is fine and
# is left alone: the onboarding step still teaches what a SIM swap is, and the
# company line in the listing still says RelayShield protects against SIM-swap
# fraud, which is true of the API and the bots.
CLAIMS = [
    "SIM swap monitoring",
    "SIM-swap monitoring",
    "SIM-swap & breach alerts",
    "SIM-swap and breach exposure alerts",
    "to enable monitoring",
]


class TestTheAppDoesNotSellWhatItDoesNotDo(unittest.TestCase):

    def test_no_surface_claims_sim_swap_monitoring_until_it_enrols(self):
        """LINE BY LINE, not file by file, for two reasons.

        A whole-file assertNotIn dumps the entire source into the failure
        message, which is unreadable and names no line. And it cannot express
        the one legitimate exemption below.
        """
        if app_enrols():
            self.skipTest("the app now posts " + ENROLL_ENDPOINT
                          + " -- the claim is earned, put the copy back")
        for path in SURFACES:
            for n, line in enumerate(code_only(path.read_text()).splitlines(), 1):
                if _about_another_product(line):
                    continue
                for claim in CLAIMS:
                    self.assertNotIn(
                        claim, line,
                        f"{path.name}:{n} claims {claim!r} for THIS APP and "
                        f"nothing calls {ENROLL_ENDPOINT}. Ship the enrol call "
                        f"or drop the claim.\n  {line.strip()[:120]}")

    def test_the_phone_field_does_not_say_what_it_is_for_when_it_is_for_nothing(self):
        if app_enrols():
            self.skipTest("enrolment ships; the field has a purpose again")
        body = code_only((APP / "src" / "screens" / "SettingsScreen.tsx").read_text())
        self.assertIn("Stored on this device", body,
                      "the phone field must say what actually happens to it")


class TestTheWrongEndpointIsNotTheFix(unittest.TestCase):
    """The trap, named before it is walked into.

    checkSimSwap() posts /v1/metered/sim-swap: a ONE-SHOT $0.25 lookup that
    enrols nothing. Wiring the function that already sits in the file would
    produce a button that charges per press and still never monitors anyone.
    Two live endpoints one character of muscle memory apart, and the wrong one
    is the one already imported.
    """

    def test_metered_sim_swap_is_never_treated_as_enrolment(self):
        api = code_only((APP / "src" / "api" / "relayshield.ts").read_text())
        if "/v1/metered/sim-swap" not in api:
            self.skipTest("the one-shot helper is gone")
        for path in APP.joinpath("src").rglob("*.tsx"):
            body = code_only(path.read_text())
            self.assertNotIn(
                "checkSimSwap", body,
                f"{path.name} calls checkSimSwap, which is the METERED one-shot "
                "lookup. Enrolment is " + ENROLL_ENDPOINT + ", and it is not "
                "metered.")


class TestTheServerHalfIsStillThere(unittest.TestCase):
    """So nobody concludes from the copy change that the feature was dropped."""

    def test_the_enrolment_endpoint_and_consent_module_exist(self):
        api = (ROOT / "relayshield_api.py").read_text()
        self.assertIn(f'"{ENROLL_ENDPOINT}"', api)
        self.assertTrue((ROOT / "relayshield_sim_swap_consent.py").exists())
        self.assertTrue((ROOT / "relayshield_sim_swap_monitor.py").exists())

    def test_cs_mobile_is_already_an_allowed_consent_source(self):
        """Somebody reserved the enum value for this surface and the call was
        never written."""
        consent = (ROOT / "relayshield_sim_swap_consent.py").read_text()
        self.assertIn('"cs_mobile"', consent)


if __name__ == "__main__":
    unittest.main(verbosity=2)
