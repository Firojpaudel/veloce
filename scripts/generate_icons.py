#!/usr/bin/env python3
"""
Renders the Veloce mark (assets/brand/veloce-app-icon.svg) to every icon the apps and extension use.

The mark is four straight-edged shapes, so it is drawn here from the same coordinates with 8x
supersampling: crisp at 16 px, no SVG renderer needed.

    python3 scripts/generate_icons.py
"""

import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INK = (23, 23, 23, 255)        # #171717
ACCENT = (37, 99, 235, 255)    # #2563eb

# Same geometry as assets/brand/veloce-app-icon.svg (1000 x 1000 canvas)
CORNER = 220
SHAPES = [
    [(120, 150), (238, 150), (474, 560), (413, 666)],
    [(286, 150), (404, 150), (554, 440), (493, 546)],
    [(452, 150), (570, 150), (634, 315), (573, 421)],
    [(570, 150), (870, 150), (590, 850), (452, 850), (740, 150)],
]


def render(size: int) -> Image.Image:
    ss = 8
    big = size * ss
    k = big / 1000
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=CORNER * k, fill=INK)
    for shape in SHAPES:
        d.polygon([(x * k, y * k) for x, y in shape], fill=ACCENT)
    return img.resize((size, size), Image.LANCZOS)


def main():
    targets = {
        "extension/icons/icon16.png": 16,
        "extension/icons/icon32.png": 32,
        "extension/icons/icon48.png": 48,
        "extension/icons/icon128.png": 128,
        "assets/icon-256.png": 256,
        "assets/logo.png": 512,
        "engine/ui/logo.png": 128,
    }
    for rel, size in targets.items():
        path = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        render(size).save(path, optimize=True)
        print(f"wrote {rel} ({size}px)")

    # Multi-resolution Windows icon (exe, installer, shortcuts); small sizes rendered directly for sharpness
    ico = os.path.join(ROOT, "assets", "veloce.ico")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    render(256).save(ico, sizes=[(s, s) for s in sizes], append_images=[render(s) for s in sizes[:-1]])
    print("wrote assets/veloce.ico")


if __name__ == "__main__":
    main()
