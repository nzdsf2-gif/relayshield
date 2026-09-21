#!/usr/bin/env python3
"""Generate a QR code for the WhatsApp front door, with its attribution key.

    python3 tools/wa_qr.py wa-devs
    python3 tools/wa_qr.py wa-print --out assets/wa/wa_qr_print.svg

WHY A TOOL AND NOT A HAND-MADE IMAGE
------------------------------------
A QR is unreadable by a human, so a wrong one is invisible until somebody scans
it and nothing happens. Two values have to be right inside it and neither may
be typed:

  THE NUMBER. wa.me answers a malformed or wrong number with HTTP 200 and an
  "invalid" page, so a broken QR looks live to every probe we own. It is read
  here out of cloudflare_worker_blog.js's WA_NUMBER, which tools/wa_front_door_
  link.py fills from Secrets Manager. Never a literal.

  THE KEY. WhatsApp has no deep-link payload, so the attribution token rides in
  the prefilled message as SRC_<key>, and relayshield_whatsapp_webhook.py's
  parse_wa_source reads it BEFORE the user lookup and strips it from the body.
  A QR carrying a friendly greeting instead logs nothing, leaves no `unmatched:`
  row to find later, and is indistinguishable from organic traffic forever.
  That is the unrecoverable mistake on this surface, and it is exactly what a
  generic QR generator produces.

SVG RATHER THAN PNG, DELIBERATELY. It scales to any print size without
regenerating, it is a text file so it needs no .gitignore exception and diffs
sensibly, and it survives the chat unchanged where a PNG arrives re-encoded as
.webp and an upload dialog greys it out.

NEEDS `qrcode` (pip install qrcode). That is a real prerequisite and it is worth
stating: this is run once per key, the OUTPUT is committed, and nobody needs the
library to use it.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NUMBER_SOURCE = ROOT / "cloudflare_worker_blog.js"


def wa_number() -> str:
    src = NUMBER_SOURCE.read_text(encoding="utf-8")
    m = re.search(r'const\s+WA_NUMBER\s*=\s*"([0-9]*)"', src)
    if not m:
        sys.exit(f"could not find WA_NUMBER in {NUMBER_SOURCE.name}")
    digits = m.group(1)
    if not digits:
        sys.exit(
            "WA_NUMBER is empty. Run this first, which reads it from Secrets\n"
            "Manager and fills every Worker that holds it as a constant:\n"
            "  AWS_PROFILE=relayshield python3 tools/wa_front_door_link.py --write")
    # E.164 without the plus, which is the form wa.me takes. Refusing here
    # rather than emitting a QR that resolves to an "invalid" page.
    if not re.fullmatch(r"[1-9][0-9]{7,14}", digits):
        sys.exit(f"WA_NUMBER {digits!r} is not E.164 digits; refusing to build a QR")
    return digits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key", help="attribution key, e.g. wa-devs. It becomes SRC_<key>.")
    ap.add_argument("--out", help="output path; default assets/wa/wa_qr_<key>.svg")
    args = ap.parse_args()

    if not re.fullmatch(r"wa-[a-z0-9-]{2,28}", args.key):
        sys.exit(f"key {args.key!r} must look like wa-something: the funnel's "
                 f"WHATSAPP stage filters on wa-[a-z0-9-]* and a key outside "
                 f"that shape is counted by nothing.")

    number = wa_number()
    url = f"https://wa.me/{number}?text=SRC_{args.key}"

    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        sys.exit("needs the qrcode package:  pip install qrcode\n"
                 "It is only needed to GENERATE; the committed .svg needs nothing.")

    # ERROR_CORRECT_M: 15% recovery. Enough for print and for a logo overlay
    # later, without inflating the module count on a URL this short.
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)

    out = Path(args.out) if args.out else ROOT / "assets" / "wa" / f"wa_qr_{args.key}.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    print(f"encodes : {url}")
    print(f"modules : {qr.modules_count}x{qr.modules_count}")
    print(f"wrote   : {out.relative_to(ROOT)}")
    print()
    print("SCAN IT BEFORE USING IT. A QR is unreadable by a human, so the only")
    print("check that means anything is a phone opening WhatsApp with the")
    print("prefilled message reading exactly:  SRC_%s" % args.key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
