#!/usr/bin/env python3
"""Generate OmniReader Pro icon assets.

Produces:
  resources/icons/omnireader.ico   (multi-size Windows icon)
  resources/icons/omnireader.png   (512px master)
  resources/icons/omnireader.svg   (vector master)

The mark: a document page with the OmniReader "converging brackets" cut —
an open book shape formed from the OR monogram, in burnt sienna on a
deep ink field, with a warm accent line. Kept geometric and flat so it
reads at 16px and at 256px.
"""
from __future__ import annotations

import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "resources" / "icons"
ICONS_DIR.mkdir(parents=True, exist_ok=True)

INK = "#14100E"
PAPER = "#F4EDE2"
ACCENT = "#C7522A"
WARM = "#E5B25D"

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="96" fill="{INK}"/>
  <!-- document page -->
  <rect x="148" y="96" width="216" height="288" rx="18" fill="{PAPER}"/>
  <rect x="148" y="96" width="216" height="288" rx="18" fill="none" stroke="#B9AC99" stroke-width="6"/>
  <!-- open-book spine cut -->
  <path d="M256 120 L256 360" stroke="{WARM}" stroke-width="10" stroke-linecap="round"/>
  <!-- left page: O of OmniReader -->
  <path d="M184 176 a32 32 0 1 0 0.1 0" fill="none" stroke="{ACCENT}" stroke-width="14" stroke-linecap="round"/>
  <!-- right page: R of OmniReader -->
  <path d="M300 176 v56" stroke="{ACCENT}" stroke-width="14" stroke-linecap="round"/>
  <path d="M300 208 a22 22 0 1 0 22 22 a14 14 0 0 0 -22 -8 l22 26" fill="none"
        stroke="{ACCENT}" stroke-width="14" stroke-linecap="round"/>
  <!-- text lines -->
  <path d="M176 300 h72" stroke="#8A7B66" stroke-width="10" stroke-linecap="round"/>
  <path d="M176 324 h56" stroke="#8A7B66" stroke-width="10" stroke-linecap="round"/>
  <path d="M288 300 h36" stroke="#8A7B66" stroke-width="10" stroke-linecap="round"/>
  <path d="M288 324 h28" stroke="#8A7B66" stroke-width="10" stroke-linecap="round"/>
  <!-- underline accent -->
  <path d="M148 420 h216" stroke="{ACCENT}" stroke-width="8" stroke-linecap="round"/>
</svg>
"""


def build_png(size: int) -> bytes:
    from PIL import Image, ImageDraw
    from PIL.Image import Resampling
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 512.0

    def R(*xy):
        return tuple(int(v * s) for v in xy)

    def C(hexv, a=255):
        h = hexv.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)

    # rounded square field
    r = R(0, 0, 512, 512)
    radius = int(96 * s)
    draw.rounded_rectangle(r, radius=radius, fill=C(INK))
    # document page
    page = R(148, 96, 364, 384)
    draw.rounded_rectangle(page, radius=int(18 * s), fill=C(PAPER))
    draw.rounded_rectangle(page, radius=int(18 * s), outline=C("#B9AC99"), width=max(1, int(6 * s)))
    # spine
    x0, y0 = R(256, 120)
    draw.line([(x0, y0), (x0, R(256, 360)[1])], fill=C(WARM), width=max(1, int(10 * s)))
    # O
    cx, cy, rad = R(200, 208, 32)
    draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=C(ACCENT),
                 width=max(1, int(14 * s)))
    # R stem + bowl + leg
    sx, sy0, sy1 = R(300, 176, 232)
    draw.line([(sx, sy0), (sx, sy1)], fill=C(ACCENT), width=max(1, int(14 * s)))
    bx, by, br = R(300, 208, 22)
    draw.ellipse([bx - br, by - br, bx + br, by + br], outline=C(ACCENT),
                 width=max(1, int(14 * s)))
    lx, ly0, ly1 = R(300, 200, 234)
    draw.line([(lx, ly0), (lx + R(0, 0, 22)[2], ly1)],
              fill=C(ACCENT), width=max(1, int(14 * s)))
    # text lines
    for (ax, ay, bx, by) in [(176, 300, 248, 300), (176, 324, 232, 324),
                             (288, 300, 324, 300), (288, 324, 316, 324)]:
        draw.line([R(ax, ay), R(bx, by)], fill=C("#8A7B66"),
                  width=max(1, int(10 * s)))
    # accent underline
    draw.line([R(148, 420), R(364, 420)], fill=C(ACCENT), width=max(1, int(8 * s)))

    if size < 256:
        img = img.resize((size, size), Resampling.LANCZOS)
    return img


def main() -> None:
    # SVG master
    (ICONS_DIR / "omnireader.svg").write_text(SVG, encoding="utf-8")
    # PNG master
    from PIL import Image
    master = build_png(512)
    master.save(ICONS_DIR / "omnireader.png")
    # ICO with common sizes. The primary image must be the largest; Pillow
    # embeds the remaining sizes from append_images.
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [build_png(s) for s in sizes]
    master_ico = imgs[-1]
    master_ico.save(ICONS_DIR / "omnireader.ico", format="ICO",
                    sizes=[(s, s) for s in sizes],
                    append_images=imgs[:-1],
                    bitmap_format="bgra")
    print("wrote", ICONS_DIR / "omnireader.ico",
          ICONS_DIR / "omnireader.png",
          ICONS_DIR / "omnireader.svg")


if __name__ == "__main__":
    main()