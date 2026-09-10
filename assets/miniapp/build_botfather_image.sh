#!/bin/sh
# Render the BotFather /newapp photo at EXACTLY 640x360.
#
# BotFather's photo step is mandatory and cannot be skipped, and it rejects a
# file that is not 640x360 -- which is what a phone screenshot or an exported
# logo always is. So the image is GENERATED at the exact size rather than
# resized by hand and hoped over.
#
# The colours are not decorative: --bg #17212b and --accent #3b82f6 are the
# `--tg-theme-bg-color` and `--tg-theme-button-color` DEFAULTS declared in
# cloudflare_worker_miniapp.js, so the listing thumbnail and the app a user
# opens are the same two colours instead of two guesses.
#
# Chromium rather than PIL: this container has no PIL and no playwright module,
# and Chromium is pre-installed for Playwright. Text rendering is also simply
# better, which matters because BotFather shows this small.
#
# Verify after any edit -- the size is the whole requirement:
#   python3 -c "import struct;d=open('assets/miniapp/idcheck_botfather_640x360.png','rb').read();print(struct.unpack('>II',d[16:24]))"
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
CHROME=/opt/pw-browsers/chromium-1194/chrome-linux/chrome
[ -x "$CHROME" ] || CHROME=$(command -v chromium || command -v google-chrome)
"$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --force-device-scale-factor=1 --window-size=640,360 \
  --screenshot="$DIR/idcheck_botfather_640x360.png" \
  "file://$DIR/idcheck_botfather_640x360.html"
python3 - "$DIR/idcheck_botfather_640x360.png" <<'PY'
import struct, sys
d = open(sys.argv[1], 'rb').read()
assert d[:8] == b'\x89PNG\r\n\x1a\n', "not a PNG"
w, h = struct.unpack('>II', d[16:24])
print(f"{w}x{h}, {len(d)/1024:.1f} KB")
if (w, h) != (640, 360):
    raise SystemExit(f"WRONG SIZE: {w}x{h}, BotFather needs exactly 640x360")
print("OK: exactly 640x360")
PY

# A JPEG COPY, AND IT IS NOT REDUNDANT. BotFather's photo step rejects a
# DOCUMENT with "send photo", and Telegram Desktop decides photo-vs-document
# partly from the file type: a PNG is the one it will most readily send
# uncompressed as a file, which is exactly the rejected path. A baseline JPEG
# with no alpha is unambiguously photo-shaped, so it removes the variable
# instead of relying on the sender ticking the right box.
#
# Pillow is not in this container and is not worth adding to it. PyPI is
# reachable, so a throwaway venv is the documented route.
VENV="${TMPDIR:-/tmp}/rs-img-venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --disable-pip-version-check Pillow
fi
"$VENV/bin/python" "$DIR/to_jpeg.py" "$DIR"
