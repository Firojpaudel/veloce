#!/usr/bin/env python3
"""
Renders the Veloce "V" mark to crisp PNG icons at every size the extension and apps need.

The mark is drawn from vector geometry (matching assets/logo.png) with 8x supersampling, instead of
downscaling one large bitmap, so the 16px/32px toolbar icons stay sharp. Small sizes drop the outer
ring and enlarge the V for legibility.

    python3 scripts/generate_icons.py
"""

import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NAVY = (15, 23, 42, 255)
RING = (125, 211, 252, 255)
BLUE = (37, 99, 235, 255)
SKY = (56, 189, 248, 255)
WHITE = (255, 255, 255, 255)

# Geometry on a 512 canvas (same as assets/logo.png)
LEFT_WING = [(112, 138), (215, 138), (247, 384), (155, 384)]
RIGHT_WING = [(400, 138), (298, 138), (228, 384), (329, 384)]
NOTCH = [(234, 138), (278, 138), (257, 238)]


def render(size: int, ring: bool) -> Image.Image:
    ss = 8
    big = size * ss
    scale = big / 512
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if ring:
        d.rounded_rectangle([20 * scale, 20 * scale, 492 * scale, 492 * scale], radius=118 * scale, fill=RING)
        d.rounded_rectangle([34 * scale, 34 * scale, 478 * scale, 478 * scale], radius=104 * scale, fill=NAVY)
        zoom = 1.0
    else:
        d.rounded_rectangle([8 * scale, 8 * scale, 504 * scale, 504 * scale], radius=120 * scale, fill=NAVY)
        zoom = 1.22  # larger V when there's no ring, for 16/32 px legibility

    def pts(poly):
        cx, cy = 256, 261
        return [((x - cx) * zoom * scale + cx * scale, (y - cy) * zoom * scale + cy * scale) for x, y in poly]

    d.polygon(pts(LEFT_WING), fill=BLUE)
    d.polygon(pts(RIGHT_WING), fill=SKY)
    d.polygon(pts(NOTCH), fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


def main():
    targets = {
        "extension/icons/icon16.png": (16, False),
        "extension/icons/icon32.png": (32, False),
        "extension/icons/icon48.png": (48, True),
        "extension/icons/icon128.png": (128, True),
        "assets/icon-256.png": (256, True),
    }
    for rel, (size, ring) in targets.items():
        path = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        render(size, ring).save(path, optimize=True)
        print(f"wrote {rel} ({size}px)")

    # Multi-resolution Windows icon for the PyInstaller executable
    ico = os.path.join(ROOT, "assets", "veloce.ico")
    render(256, True).save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote assets/veloce.ico")


if __name__ == "__main__":
    main()
