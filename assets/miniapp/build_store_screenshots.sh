#!/bin/sh
# Render the catalogue store screenshots at EXACTLY 900x1600.
#
# ton.app states "Required resolution: 900x1600px" -- required, not maximum --
# and an iPhone screenshot is 1179x2556, a different aspect ratio (9:19.5
# against 9:16). So a resize distorts and a centre crop eats the app's own
# header. Generating at the exact size removes the problem, exactly as
# build_botfather_image.sh does for BotFather's mandatory 640x360.
#
# TWO THINGS HERE ARE NOT INCIDENTAL AND BOTH WERE FOUND BY RUNNING IT.
#
# 1. IT IS SERVED OVER HTTP, NOT OPENED FROM file://. The page module begins
#    `import { check } from "/relayshield-widget.js"` -- an ABSOLUTE path, which
#    on file:// resolves to the filesystem root and 404s. A module whose import
#    fails runs NOTHING while the static HTML renders perfectly, so the first
#    run of this script produced four screenshots of the boot watchdog's own
#    error banner. That is the exact failure the watchdog was built to make
#    visible, catching a screenshot rig instead of a deploy.
#
# 2. IT RENDERS AT A PHONE VIEWPORT AND DOWNSCALES, RATHER THAN SHOOTING
#    900x1600 DIRECTLY. A 900px-wide viewport lays the page out for a desktop:
#    wide, short, and two thirds empty background. A phone viewport is what a
#    catalogue browser expects and what the app is actually used on.
#
#    AND HEADLESS CHROMIUM ENFORCES A MINIMUM WINDOW WIDTH OF 500 CSS PIXELS.
#    Measured, not read: --window-size=390, 450 and 500 all report
#    documentElement.clientWidth === 500, while the SCREENSHOT is still taken at
#    the size asked for -- so requesting 450 lays the page out at 500 and then
#    crops 50 CSS pixels off the right edge. The first phone-width run silently
#    cut the third tab and the right half of the Check it button. So the shot is
#    taken at 500x889 (9:16) at 2x, giving 1000x1778, and Pillow resamples that
#    to exactly 900x1600.
#
# It renders the SERVED page rather than the Worker source: tools/miniapp_render.mjs
# runs the Worker and prints the bytes a browser receives. Screenshotting
# anything else is the extractor-does-not-match-the-artefact defect that has
# already cost this repo one live outage.
#
# Run it after ANY Mini App change that alters these screens, and re-upload --
# a store screenshot is a claim about the current product.
#
#   sh assets/miniapp/build_store_screenshots.sh
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$DIR/../.." && pwd)
WORK="${TMPDIR:-/tmp}/rs-shots"
OUT="$DIR/store"
PORT=${RS_SHOT_PORT:-8731}
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

CHROME=/opt/pw-browsers/chromium-1194/chrome-linux/chrome
[ -x "$CHROME" ] || CHROME=$(command -v chromium || command -v google-chrome)

node "$ROOT/tools/miniapp_render.mjs" > "$WORK/page.html"
node "$ROOT/tools/miniapp_render.mjs" --widget > "$WORK/relayshield-widget.js"
python3 "$DIR/stage_store_screenshots.py" "$WORK/page.html" "$WORK" >/dev/null

python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$WORK" >/dev/null 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true' EXIT
# Wait for the port rather than sleeping a guessed amount.
n=0
while [ "$n" -lt 50 ]; do
  if python3 -c "import socket,sys; s=socket.socket(); sys.exit(s.connect_ex(('127.0.0.1',$PORT)))" 2>/dev/null; then
    break
  fi
  n=$((n + 1))
done
[ "$n" -lt 50 ] || { echo "the staging server never came up on $PORT"; exit 1; }

i=1
for stage in check refusal watch learn; do
  name=$(printf "%02d_%s" "$i" "$stage")
  "$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --force-device-scale-factor=2 --window-size=500,889 \
    --virtual-time-budget=6000 \
    --screenshot="$WORK/$name.png" \
    "http://127.0.0.1:$PORT/stage_$stage.html" 2>/dev/null
  i=$((i + 1))
done

# Pillow is not in this container and is not worth adding to it. PyPI is
# reachable, so a throwaway venv is the documented route -- the same one
# build_botfather_image.sh already uses for its JPEG copy.
VENV="${TMPDIR:-/tmp}/rs-img-venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --disable-pip-version-check Pillow
fi
"$VENV/bin/python" "$DIR/resize_store_screenshots.py" "$WORK" "$OUT"

# THE SIZE IS THE WHOLE REQUIREMENT, and so is the absence of the watchdog
# banner: a screenshot of a page whose code did not start looks fine at a
# glance and is the single worst thing to put in a catalogue.
python3 - "$OUT" <<'PY'
import pathlib, struct, sys, zlib
out = pathlib.Path(sys.argv[1])
shots = sorted(out.glob("*.png"))
if not shots:
    raise SystemExit("no screenshots were written")
bad, sizes = [], set()
for p in shots:
    d = p.read_bytes()
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        bad.append(f"{p.name}: not a PNG")
        continue
    w, h = struct.unpack(">II", d[16:24])
    kb = len(d) / 1024
    print(f"{p.name}: {w}x{h}, {kb:.1f} KB")
    sizes.add(len(d))
    if (w, h) != (900, 1600):
        bad.append(f"{p.name}: {w}x{h}, ton.app requires exactly 900x1600")
    if kb > 10 * 1024:
        bad.append(f"{p.name}: {kb/1024:.1f} MB, over the 10 MB cap")
# Four byte-identical files means the staging script never drove the page --
# which is how the file:// failure presented, silently and plausibly.
if len(sizes) == 1 and len(shots) > 1:
    bad.append("every screenshot is byte-identical: the staging script did not run")
if bad:
    raise SystemExit("\n".join(bad))
print(f"OK: {len(shots)} screenshots, all exactly 900x1600")
PY
