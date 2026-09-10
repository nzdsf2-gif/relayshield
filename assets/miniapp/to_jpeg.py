"""PNG -> JPEG for the BotFather photo. Asserts the size; that is the point.

Kept as its own file rather than a heredoc inside the shell script: nesting a
Python heredoc inside a shell heredoc is how the first attempt at this mangled
itself, and a converter that silently half-wrote would be worse than one that
is simply a file.
"""
import os
import sys

from PIL import Image

d = sys.argv[1]
src = os.path.join(d, "idcheck_botfather_640x360.png")
dst = os.path.join(d, "idcheck_botfather_640x360.jpg")

Image.open(src).convert("RGB").save(dst, "JPEG", quality=92, optimize=True)

out = Image.open(dst)
print(f"{out.size[0]}x{out.size[1]} JPEG, {os.path.getsize(dst) / 1024:.1f} KB")
if out.size != (640, 360):
    raise SystemExit(f"WRONG SIZE: {out.size}, BotFather needs exactly 640x360")
if out.mode != "RGB":
    raise SystemExit(f"WRONG MODE: {out.mode}, an alpha channel is not photo-shaped")
print("OK: JPEG exactly 640x360, no alpha")
