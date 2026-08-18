"""Rebuild developers-og.png with live-checked figures.

Colours and layout sampled directly from the 2026-07-30 card so the only visible
change is the five numbers. Run, eyeball the PNG, then re-embed the base64 in
developers_og_image.js.
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG      = (13, 15, 20)
INDIGO  = (108, 99, 255)
WHITE   = (232, 234, 240)
URLCOL  = (98, 91, 220)
GREEN   = (34, 197, 94)
LABEL   = (139, 145, 168)
DIVIDER = (36, 40, 54)

B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
R = "/System/Library/Fonts/Supplemental/Arial.ttf"
f = lambda p, s: ImageFont.truetype(p, s)

im = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(im)

d.rectangle([0, 0, W, 6], fill=INDIGO)

d.text((72, 74),  "RelayShield", font=f(B, 44), fill=WHITE)
d.text((72, 131), "api.relayshield.net/developers", font=f(R, 23), fill=URLCOL)

d.text((72, 213), "Security intelligence",   font=f(B, 74), fill=WHITE)
d.text((72, 297), "for developers & agents", font=f(B, 74), fill=INDIGO)

# LIVE-CHECKED 2026-08-12 (31 = len(METERED_CREDIT_COSTS) after dependency-risk). See the header comment in developers_og_image.js for
# the exact re-check commands; do not update one of these without the others.
# Five tiles as of 2026-08-17: sightings added alongside distinct indicators,
# because "indicators" alone was the number that conflated the two. Spacing is
# 1056 usable px (W - 2*72 margin) / 5 = 211, down from 267 for four tiles.
STATS = [
    ("494K+", "Indicators",         72),
    ("5.8M+", "Sightings",         283),
    ("95",    "monitored channels", 494),
    ("20",    "threat feeds",      705),
    ("31",    "API endpoints",     916),
]
for value, label, x in STATS:
    d.text((x, 415), value, font=f(B, 38), fill=GREEN)
    d.text((x, 465), label, font=f(R, 21), fill=LABEL)

d.rectangle([72, 529, W - 72, 530], fill=DIVIDER)

x = 72
for i, chip in enumerate(["REST", "MCP", "STIX/TAXII 2.1", "MISP", "x402"]):
    if i:
        d.text((x, 563), "·", font=f(R, 24), fill=(96, 102, 122))
        x += 28
    d.text((x, 561), chip, font=f(R, 24), fill=LABEL)
    x += d.textlength(chip, font=f(R, 24)) + 26

im.save("og_new.png")
print("wrote og_new.png", im.size)
