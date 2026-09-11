#!/usr/bin/env python3
"""Generate Veyrion Workspace icon assets.

Produces:
  resources/icons/veyrion.ico   (multi-size Windows icon)
  resources/icons/veyrion.png   (512px master)
  resources/icons/veyrion.svg   (vector master)

The mark: a document page with a folded corner and a bold geometric "V"
for Veyrion, in burnt sienna on a deep ink field, finished with a warm
accent underline. Deliberately flat and heavy-stroked so it survives
rendering at 16px in the taskbar as well as at 256px in the installer.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "resources" / "icons"
ICONS_DIR.mkdir(parents=True, exist_ok=True)

INK = "#14100E"
PAPER = "#F4EDE2"
FOLD = "#E3D8C6"
RULE = "#B9AC99"
MUTED = "#8A7B66"
ACCENT = "#C7522A"
WARM = "#E5B25D"

# Geometry (512 grid)
PAGE = (148, 96, 364, 384)          # x0, y0, x1, y1
CUT = 76                            # folded-corner size
MARK = ((188, 196), (256, 274), (324, 196))

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="96" fill="{INK}"/>
  <!-- document page with a folded top-right corner -->
  <path d="M148 114 a18 18 0 0 1 18 -18 h122 l76 76 v194 a18 18 0 0 1 -18 18 h-180
           a18 18 0 0 1 -18 -18 z" fill="{PAPER}" stroke="{RULE}" stroke-width="6"/>
  <path d="M288 96 l76 76 h-58 a18 18 0 0 1 -18 -18 z" fill="{FOLD}" stroke="{RULE}" stroke-width="6"/>
  <!-- Veyrion mark -->
  <path d="M188 196 L256 274 L324 196" fill="none" stroke="{ACCENT}"
        stroke-width="20" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- baseline rules -->
  <path d="M176 312 h72" stroke="{MUTED}" stroke-width="10" stroke-linecap="round"/>
  <path d="M176 336 h44" stroke="{MUTED}" stroke-width="10" stroke-linecap="round"/>
  <!-- warm accent underline -->
  <path d="M148 420 h216" stroke="{ACCENT}" stroke-width="8" stroke-linecap="round"/>
</svg>
"""


def build_png(size: int):
    from PIL import Image, ImageDraw
    from PIL.Image import Resampling

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 512.0

    def R(*xy):
        return tuple(int(round(v * s)) for v in xy)

    def C(hexv, a=255):
        h = hexv.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)

    def w(px):
        return max(1, int(round(px * s)))

    # Rounded ink field.
    draw.rounded_rectangle(R(0, 0, 512, 512), radius=int(96 * s), fill=C(INK))

    x0, y0, x1, y1 = PAGE
    r = int(18 * s)

    # Page silhouette with the top-right corner cut away, built from two
    # rectangles plus the diagonal cut so it matches the SVG path closely.
    draw.rounded_rectangle(R(x0, y0, x1, y1), radius=r, fill=C(PAPER),
                           outline=C(RULE), width=w(6))
    draw.polygon([R(x1 - CUT, y0 - 2), R(x1 + 2, y0 - 2), R(x1 + 2, y0 + CUT)],
                 fill=C(INK))
    # Fold flap.
    draw.polygon([R(x1 - CUT, y0), R(x1, y0 + CUT), R(x1 - CUT, y0 + CUT)],
                 fill=C(FOLD), outline=C(RULE))
    draw.line([R(x1 - CUT, y0), R(x1, y0 + CUT)], fill=C(RULE), width=w(4))

    # Veyrion "V".
    draw.line([R(*MARK[0]), R(*MARK[1]), R(*MARK[2])], fill=C(ACCENT),
              width=w(20), joint="curve")

    # Baseline rules.
    draw.line([R(176, 312), R(248, 312)], fill=C(MUTED), width=w(10))
    draw.line([R(176, 336), R(220, 336)], fill=C(MUTED), width=w(10))

    # Accent underline.
    draw.line([R(148, 420), R(364, 420)], fill=C(ACCENT), width=w(8))

    if size != 512:
        img = img.resize((size, size), Resampling.LANCZOS)
    return img


def main() -> None:
    (ICONS_DIR / "veyrion.svg").write_text(SVG, encoding="utf-8")

    master = build_png(512)
    master.save(ICONS_DIR / "veyrion.png")

    # The primary image must be the largest; Pillow embeds the rest.
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [build_png(s) for s in sizes]
    imgs[-1].save(ICONS_DIR / "veyrion.ico", format="ICO",
                  sizes=[(s, s) for s in sizes],
                  append_images=imgs[:-1],
                  bitmap_format="bgra")
    print("wrote", ICONS_DIR / "veyrion.ico",
          ICONS_DIR / "veyrion.png",
          ICONS_DIR / "veyrion.svg")


if __name__ == "__main__":
    main()
