#!/bin/sh
# Render a 512x512 square catalogue icon from one of the *_icon_512.html files.
#
#   sh assets/miniapp/build_icon_512.sh relayshield_icon_512
#
# Catalogue icon fields want SQUARE, minimum 256x256, and relayshield_logo.png
# is 1920x1080 -- 16:9, so every square crop of it loses either the shield or
# the wordmark. Generating at the exact size removes the crop entirely.
#
# @2x then downscale is deliberate: Chromium renders text markedly better at
# 1024 and the result is resampled once, where a direct 512 render hints the
# glyphs and looks muddy at the 80-120px a catalogue grid actually shows.
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
NAME=${1:-relayshield_icon_512}
[ -f "$DIR/$NAME.html" ] || { echo "no such source: $DIR/$NAME.html"; exit 2; }
CHROME=/opt/pw-browsers/chromium-1194/chrome-linux/chrome
[ -x "$CHROME" ] || CHROME=$(command -v chromium || command -v google-chrome)
"$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --force-device-scale-factor=2 --window-size=512,512 \
  --screenshot="$DIR/$NAME.png" "file://$DIR/$NAME.html"
VENV="${TMPDIR:-/tmp}/rs-img-venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --disable-pip-version-check Pillow
fi
"$VENV/bin/python" - "$DIR/$NAME.png" <<'PY'
import sys
from PIL import Image
p = sys.argv[1]
im = Image.open(p)
if im.size != (512, 512):
    im = im.convert("RGB").resize((512, 512), Image.LANCZOS)
    im.save(p, "PNG", optimize=True)
im = Image.open(p)
print(f"{p}: {im.size[0]}x{im.size[1]}, {im.mode}")
if im.size != (512, 512):
    raise SystemExit("WRONG SIZE")
# THE WORDMARK MUST NOT TOUCH THE EDGE. An overflowing wordmark is clipped
# silently by overflow:hidden, and a catalogue tile reading "RelayShiel" is
# the kind of defect nobody notices until a stranger does.
#
# IT KEYS ON BRIGHTNESS, NOT ON A SAMPLED BACKGROUND PIXEL, and the first
# version did the latter and failed on a correct render. The background is two
# radial gradients over #17212b, one of them anchored at 6% -- so a single
# sampled pixel differs from its own column by more than any threshold worth
# having, and the guard flagged the gradient it was standing in. The glyphs are
# #f5f5f5 and #3b82f6 against a background whose brightest point is far below
# either, so luminance separates them with no sampling at all.
px = im.convert("RGB").load()
def bright_in_column(x):
    return any(sum(px[x, y]) / 3 > 120 for y in range(512))
edges = [x for x in (0, 1, 2, 3, 508, 509, 510, 511) if bright_in_column(x)]
if edges:
    raise SystemExit(f"CONTENT REACHES THE EDGE at columns {edges}: clipped")
print("OK: 512x512, nothing clipped at either edge")
PY
