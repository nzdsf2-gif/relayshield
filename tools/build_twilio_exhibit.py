"""
Assemble the Twilio "User Experience Screenshots" exhibit PDF.

Input : real PNG screen captures taken off the Android emulator via `adb exec-out screencap`.
Output: one letter-size PDF, one screen per page, each with a factual caption.

Nothing here draws or simulates a UI. If a source PNG is missing the script fails loudly
rather than producing a page without evidence behind it.
"""

import os
import sys

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# ReportLab's default Helvetica is a base-14 font and is NOT embedded, so the
# glyphs resolve only on a machine that already has it. A first cut of this
# exhibit rendered as tofu boxes under pdftocairo while looking fine in macOS
# Preview. This document goes to an external reviewer on an unknown platform,
# so every face it uses is embedded.
_FONT_DIR = "/System/Library/Fonts/Supplemental"
_FACES = {
    "Body": "Arial.ttf",
    "Body-Bold": "Arial Bold.ttf",
    "Body-Italic": "Arial Italic.ttf",
}
for _name, _file in _FACES.items():
    _path = os.path.join(_FONT_DIR, _file)
    if not os.path.exists(_path):
        sys.exit(f"FATAL: font {_path} not found; refusing to emit a PDF with unembedded fonts.")
    pdfmetrics.registerFont(TTFont(_name, _path))

FONT, FONT_BOLD, FONT_ITALIC = "Body", "Body-Bold", "Body-Italic"

SCRATCH = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SCRATCH, "RelayShield_SIMSwap_UserExperience_Screenshots.pdf")

PAGE_W, PAGE_H = letter
MARGIN = 0.75 * inch

HEADER = "RelayShield LLC - SIM Swap Monitoring - User Experience Screenshots"
SUBHEAD = (
    "Application: Crypto Shield Mobile v1.5.0 (net.relayshield.cryptoshieldmobile)   |   "
    "Twilio Account SID: ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
)

PAGES = [
    {
        "file": "shot1_phone_step.png",
        "title": "1. Phone number collection, with purpose stated before any lookup",
        "body": [
            "The mobile number is collected during onboarding, from the end user, on a screen titled",
            '"SIM swap monitoring". The field is labelled "Phone Number (optional)" and the step can be',
            "skipped, so monitoring is opt-in rather than a condition of using the app.",
            "",
            "The on-screen copy states the purpose directly: the number is used to enable SIM swap",
            "monitoring for the accounts the user signs in to. No lookup is performed against any number",
            "until the user has entered it here and completed onboarding.",
            "",
            "RelayShield never accepts a number submitted by one person about another. The only numbers",
            "checked are numbers their own owner entered on this screen.",
        ],
    },
    {
        "file": "shot2_consent.png",
        "detail": "shot2_consent_detail.png",
        "detail_caption": "Detail: the consent line at the foot of the same screen, enlarged for legibility.",
        "title": "2. Consent to the Terms of Service and Privacy Policy",
        "body": [
            'Shown on the first onboarding screen: "By continuing, you agree to our Terms of Service and',
            'Privacy Policy." Both are live links, and the user passes this screen before reaching the',
            "phone number step above.",
            "",
            "   Terms of Service:  https://terms.relayshield.net",
            "   Privacy Policy:    https://privacy.relayshield.net",
            "",
            "Privacy Policy section 4, SIM Swap Monitoring, discloses that an enrolled number is sent to",
            "Twilio as RelayShield's telecommunications data provider to check whether the SIM or carrier",
            "has changed, that nothing else about the user is sent, that the result is used only to alert",
            "the number's own owner, and that consent may be withdrawn at any time by removing the number.",
            "",
            "Terms of Service section 1a requires the user to own or control any number they enroll and",
            "forbids looking up a number belonging to anyone else.",
        ],
    },
]


def draw_page(c, spec):
    src = os.path.join(SCRATCH, spec["file"])
    if not os.path.exists(src):
        sys.exit(f"FATAL: missing screenshot {src}. Capture it before building the exhibit.")

    c.setFont(FONT_BOLD, 10)
    c.drawString(MARGIN, PAGE_H - MARGIN + 6, HEADER)
    c.setFont(FONT, 7.5)
    c.setFillGray(0.35)
    c.drawString(MARGIN, PAGE_H - MARGIN - 6, SUBHEAD)
    c.setFillGray(0)

    y = PAGE_H - MARGIN - 30
    c.setFont(FONT_BOLD, 12)
    c.drawString(MARGIN, y, spec["title"])
    y -= 18

    c.setFont(FONT, 9)
    for line in spec["body"]:
        c.drawString(MARGIN, y, line)
        y -= 12

    y -= 10

    detail = spec.get("detail")
    detail_path = os.path.join(SCRATCH, detail) if detail else None
    if detail_path and not os.path.exists(detail_path):
        sys.exit(f"FATAL: missing detail crop {detail_path}.")

    # Reserve room at the foot of the page for the enlarged detail strip.
    reserve = 0
    if detail_path:
        d = Image.open(detail_path)
        d_w = PAGE_W - 2 * MARGIN
        d_h = d.height * (d_w / d.width)
        reserve = d_h + 26

    img = Image.open(src)
    avail_h = y - MARGIN - reserve
    avail_w = PAGE_W - 2 * MARGIN
    scale = min(avail_w / img.width, avail_h / img.height)
    w, h = img.width * scale, img.height * scale
    x = (PAGE_W - w) / 2
    c.drawImage(src, x, y - h, width=w, height=h)

    c.setStrokeGray(0.75)
    c.rect(x, y - h, w, h)

    if detail_path:
        dy = y - h - reserve + 14
        c.drawImage(detail_path, MARGIN, dy, width=d_w, height=d_h)
        c.rect(MARGIN, dy, d_w, d_h)
        c.setFont(FONT_ITALIC, 7.5)
        c.setFillGray(0.4)
        c.drawString(MARGIN, dy - 10, spec["detail_caption"])
        c.setFillGray(0)

    c.setFont(FONT_ITALIC, 7)
    c.setFillGray(0.45)
    c.drawCentredString(
        PAGE_W / 2,
        MARGIN - 12,
        f"Unmodified screen capture from Crypto Shield Mobile v1.5.0 running on Android. Source: {spec['file']}",
    )
    c.setFillGray(0)
    c.showPage()


def main():
    c = canvas.Canvas(OUT, pagesize=letter)
    c.setTitle("RelayShield SIM Swap - User Experience Screenshots")
    c.setAuthor("RelayShield LLC")
    for spec in PAGES:
        draw_page(c, spec)
    c.save()
    print(f"WROTE {OUT}  ({os.path.getsize(OUT):,} bytes, {len(PAGES)} pages)")


if __name__ == "__main__":
    main()
