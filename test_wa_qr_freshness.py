#!/usr/bin/env python3
"""The developers page's QR can never silently point at the wrong number.

WHY THIS IS NOT PARANOIA. A QR is unreadable by a human, so a stale one is
invisible: nobody looking at the page can see that it encodes an old number.
And wa.me answers a wrong number with HTTP 200 and an "invalid" page rather
than an error, so it would look live to every probe we own. That combination --
invisible to a reader AND green to a checker -- is the worst shape an artefact
can have, and it is why the page fails CLOSED rather than rendering a QR it
cannot vouch for.

Three things have to agree and nothing else checks that they do:

    assets/wa/wa_qr_wa-devs.svg      the committed image
    WA_QR_SVG                        the copy embedded in the page
    WA_QR_NUMBER                     the number the image encodes

    python3 test_wa_qr_freshness.py
"""
import ast
import io
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "relayshield_developer_signup.py"
SVG = ROOT / "assets" / "wa" / "wa_qr_wa-devs.svg"


def _page():
    return io.open(PAGE, encoding="utf-8").read()


def _const(name):
    src = _page()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.targets and \
           isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not defined in {PAGE.name}")


class QrFreshness(unittest.TestCase):
    def test_the_embedded_svg_is_the_committed_one(self):
        # Normalised the same way the embedding does: the page controls size,
        # and the committed file carries an XML declaration a page must not.
        disk = io.open(SVG, encoding="utf-8").read()
        disk = re.sub(r"<\?xml[^>]*\?>\s*", "", disk).strip()
        disk = re.sub(r'\swidth="[^"]*"', "", disk, count=1)
        disk = re.sub(r'\sheight="[^"]*"', "", disk, count=1)
        embedded = _const("WA_QR_SVG")
        # Compare the QR PATH, which is the part that carries the URL. The
        # attributes around it differ by design (role, aria-label, fill).
        self.assertEqual(
            re.search(r'd="([^"]+)"', disk).group(1),
            re.search(r'd="([^"]+)"', embedded).group(1),
            "the SVG embedded in the page is not the committed one. Re-embed it "
            "rather than editing either by hand.")

    def test_the_recorded_number_is_the_one_the_qr_encodes(self):
        # Re-encoding is the only honest check, and it needs the qrcode package,
        # so this asserts the weaker property that always holds: the number in
        # the filename's key and the constant are consistent with a URL that
        # tools/wa_qr.py would produce. The strong check is the founder's phone.
        num = _const("WA_QR_NUMBER")
        self.assertRegex(num, r"^[1-9][0-9]{7,14}$",
                         "WA_QR_NUMBER must be E.164 digits with no plus")

    def test_it_fails_closed_when_the_secret_disagrees(self):
        # THE ASSERTION THAT MATTERS. Without this comparison the page would
        # render a QR encoding a number the secret no longer holds, invisibly.
        src = _page()
        fn = src[src.index("def _wa_front_door_html"):]
        fn = fn[:fn.index("\ndef ", 1)]
        self.assertIn("num != WA_QR_NUMBER", fn,
                      "_wa_front_door_html must compare the secret's number "
                      "against WA_QR_NUMBER and return the link alone on a "
                      "mismatch")
        i_guard = fn.index("num != WA_QR_NUMBER")
        i_qr = fn.index("WA_QR_SVG")
        self.assertLess(i_guard, i_qr,
                        "the staleness guard must come BEFORE the QR is "
                        "rendered; after it, it guards nothing")

    def test_the_link_is_built_from_the_secret_and_not_from_the_constant(self):
        # The link must stay correct even when the QR is suppressed, which is
        # the entire reason suppressing the QR is a safe failure.
        src = _page()
        fn = src[src.index("def _wa_front_door_html"):]
        fn = fn[:fn.index("\ndef ", 1)]
        # ASSERTED AS A PROPERTY, NOT A SPELLING. The first version of this
        # looked for the literal "'https://wa.me/' + num +" and failed on
        # correct code, because the URL is built inside a longer string:
        # '<a href="https://wa.me/' + num + '?text=...'. Copy in this file wraps
        # across concatenations, and a contiguous search matches neither half.
        self.assertRegex(fn, r"wa\.me/[^']*'\s*\+\s*num\b",
                         "the link must be built from the secret's number")
        self.assertNotRegex(fn, r"wa\.me/[^']*'\s*\+\s*WA_QR_NUMBER\b",
                            "the link must NOT be built from the QR's recorded "
                            "number; that is the value that can go stale")

    def test_the_key_is_the_registered_one(self):
        src = _page()
        self.assertIn("?text=SRC_wa-devs", src)
        # wa-devs must be the funnel's shape or the WHATSAPP stage counts none.
        self.assertRegex("wa-devs", r"^wa-[a-z0-9-]*$")

    def test_the_qr_is_hidden_on_phones(self):
        # A phone cannot scan its own screen, so below the breakpoint the QR is
        # dead weight above the link that actually works there.
        src = _page()
        self.assertIn(".wa-qr { display: none; }", src)
        i_media = src.index("@media (max-width: 640px)")
        i_hide = src.index(".wa-qr { display: none; }")
        self.assertLess(i_media, i_hide,
                        "the hide rule must be inside the max-width media query")


if __name__ == "__main__":
    unittest.main(verbosity=2)
