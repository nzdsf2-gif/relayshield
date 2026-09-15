#!/usr/bin/env python3
"""Resample the staged 1000x1778 captures to exactly 900x1600.

Separate from build_store_screenshots.sh because it runs under the throwaway
Pillow venv rather than the system python, and a heredoc inside a heredoc is
how the first version of this broke.
"""
import pathlib, sys
from PIL import Image


def main() -> int:
    work, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    shots = sorted(work.glob("[0-9][0-9]_*.png"))
    if not shots:
        raise SystemExit("no captures to resample")
    for src in shots:
        with Image.open(src) as im:
            im.convert("RGB").resize((900, 1600), Image.LANCZOS).save(
                out / src.name, optimize=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
