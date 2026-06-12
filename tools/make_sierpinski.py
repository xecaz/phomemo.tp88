#!/usr/bin/env python3
"""Generate a Sierpiński triangle at the TP88's native resolution.

The TP88 head is 1728 dots wide (~1600 usable) at 200 dpi. To avoid any
resampling we render directly at device pixels.

By default the gasket is drawn as **line art** — only the triangle edges, with a
capped line width (--line-width, default 2) — because solid fills merge fine
detail into chunky blobs and waste ink/paper on a stencil. Use --fill for the
old solid-triangle look.

Pure 1-bit black/white (no anti-aliasing) so the printer threshold path keeps
edges crisp. Run with the project venv:

    TiMini-Print/.venv/bin/python tools/make_sierpinski.py OUT.png [--depth N]
"""
from __future__ import annotations

import argparse
import math

from PIL import Image, ImageDraw

# Native device geometry (see docs/tp88-protocol.md).
USABLE_DOTS = 1600          # printable width in dots
A4_HEIGHT_DOTS = 2338       # 297 mm @ 200 dpi


def sierpinski(draw: ImageDraw.ImageDraw, p1, p2, p3, depth: int,
               *, fill: bool, lw: int) -> None:
    """Recursively draw the gasket. p1=apex, p2/p3=base corners.

    Leaf triangles are either filled solid (fill=True) or stroked as outlines of
    width ``lw`` (fill=False). Stroking only the leaves still draws every edge of
    the whole gasket, since the leaves tile it.
    """
    if depth == 0:
        if fill:
            draw.polygon([p1, p2, p3], fill=0)          # 0 = black = burn
        else:
            draw.polygon([p1, p2, p3], outline=0, width=lw)
        return
    m12 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    m13 = ((p1[0] + p3[0]) / 2, (p1[1] + p3[1]) / 2)
    m23 = ((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
    sierpinski(draw, p1, m12, m13, depth - 1, fill=fill, lw=lw)   # top
    sierpinski(draw, m12, p2, m23, depth - 1, fill=fill, lw=lw)   # bottom-left
    sierpinski(draw, m13, m23, p3, depth - 1, fill=fill, lw=lw)   # bottom-right


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", help="output PNG path")
    ap.add_argument("--width", type=int, default=USABLE_DOTS)
    ap.add_argument("--height", type=int, default=A4_HEIGHT_DOTS,
                    help="page/canvas height in dots")
    ap.add_argument("--depth", type=int, default=8,
                    help="recursion depth (higher = finer mesh)")
    ap.add_argument("--margin", type=int, default=4,
                    help="white border in dots")
    ap.add_argument("--equilateral", action="store_true",
                    help="true 60° triangle (height = base*√3/2), centered on the page")
    ap.add_argument("--line-width", type=int, default=2,
                    help="stroke width in dots for outline mode (default 2)")
    ap.add_argument("--fill", action="store_true",
                    help="draw solid filled triangles instead of outlines")
    args = ap.parse_args()

    w, h, m = args.width, args.height, args.margin
    img = Image.new("1", (w, h), 1)  # 1 = white background
    draw = ImageDraw.Draw(img)

    if args.equilateral:
        base = w - 2 * m
        tri_h = base * math.sqrt(3) / 2
        top_y = (h - tri_h) / 2          # center vertically on the page
        apex = ((w - 1) / 2, top_y)
        bl = (m, top_y + tri_h)
        br = (w - 1 - m, top_y + tri_h)
    else:
        apex = ((w - 1) / 2, m)
        bl = (m, h - 1 - m)
        br = (w - 1 - m, h - 1 - m)
    sierpinski(draw, apex, bl, br, args.depth,
               fill=args.fill, lw=args.line_width)

    span_h = (br[1] - apex[1])
    leaf_edge = (br[0] - bl[0]) / (2 ** args.depth)
    img.save(args.out)
    mode = "fill" if args.fill else f"outline lw={args.line_width}"
    print(f"wrote {args.out}  canvas {w}x{h}  depth={args.depth}  {mode}  "
          f"triangle span {br[0]-bl[0]:.0f}x{span_h:.0f}  "
          f"smallest edge ~{leaf_edge:.1f}px")


if __name__ == "__main__":
    main()
