"""Generate a synthetic TP88 test strip (border + diagonals + label).

The strip is 1600 px wide to match the printer's usable width (1728-dot head,
~1600 usable) so geometry/scaling can be checked on real paper.

Usage: python tools/make_test_strip.py [out.png]
"""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw

WIDTH, HEIGHT = 1600, 120


def make(path: str) -> None:
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline=0, width=3)
    d.line([0, 0, WIDTH - 1, HEIGHT - 1], fill=0, width=2)
    d.line([0, HEIGHT - 1, WIDTH - 1, 0], fill=0, width=2)
    d.text((20, 40), "TP88 TEST STRIP", fill=0)
    img.save(path)
    print(f"wrote {path} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "tp88_test.png")
