#!/usr/bin/env python3
"""
Renders the README benchmark chart (grouped horizontal bars) as static SVG, light and dark variants.

    python3 scripts/render_benchmark_chart.py

Data: mean MB/s of 3 alternating runs per source, measured 2026-11-12 on one home connection.
Update RESULTS after re-running the benchmark.
Palette: categorical slots 1-3 (blue / orange / aqua), validated all-pairs: CVD ΔE ≥ 9.2 in both modes.
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERIES = [
    ("Veloce 1.1 (adaptive)", "new"),
    ("Veloce 1.0 (fixed 16)", "old"),
    ("Single stream (browser-like)", "single"),
]
RESULTS = [  # (source, size, {series: MB/s})
    ("Internet Archive", "59 MB", {"new": 5.33, "old": 4.47, "single": 0.43}),
    ("Kernel.org CDN", "6.6 MB", {"new": 10.39, "old": 5.62, "single": 11.05}),
    ("Python.org (Fastly)", "19 MB", {"new": 8.35, "old": 7.47, "single": 6.97}),
    ("Apache archive", "9.4 MB", {"new": 2.59, "old": 2.84, "single": 1.42}),
    ("SoundHelix", "8.5 MB", {"new": 1.50, "old": 1.78, "single": 1.87}),
]
THEMES = {
    "light": {"surface": "#ffffff", "text": "#1f2328", "muted": "#59636e", "grid": "#d1d9e0",
              "series": ["#2a78d6", "#eb6834", "#1baf7a"]},
    "dark": {"surface": "#0d1117", "text": "#e6edf3", "muted": "#9198a1", "grid": "#30363d",
             "series": ["#3987e5", "#d95926", "#199e70"]},
}


def render(t: dict) -> str:
    W, left, right, top = 760, 170, 64, 74
    bar_h, bar_gap, group_gap = 11, 2, 22
    group_h = len(SERIES) * bar_h + (len(SERIES) - 1) * bar_gap
    plot_h = len(RESULTS) * group_h + (len(RESULTS) - 1) * group_gap
    H = top + plot_h + 60
    max_v = 12.0
    x = lambda v: left + v / max_v * (W - left - right)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif" role="img" '
        f'aria-label="Download throughput in MB/s per source for Veloce 1.1, Veloce 1.0 and a single stream">',
        f'<rect width="{W}" height="{H}" rx="10" fill="{t["surface"]}"/>',
        f'<text x="20" y="30" font-size="15" font-weight="600" fill="{t["text"]}">Throughput by source (MB/s, higher is better)</text>',
    ]
    lx = 20
    for i, (label, _) in enumerate(SERIES):
        out.append(f'<rect x="{lx}" y="44" width="12" height="12" rx="3" fill="{t["series"][i]}"/>')
        out.append(f'<text x="{lx + 18}" y="54" font-size="12" fill="{t["muted"]}">{label}</text>')
        lx += 18 + len(label) * 6.6 + 22

    for v in range(0, 13, 2):
        gx = x(v)
        out.append(f'<line x1="{gx:.1f}" y1="{top - 6}" x2="{gx:.1f}" y2="{top + plot_h + 4}" stroke="{t["grid"]}" stroke-width="1"/>')
        out.append(f'<text x="{gx:.1f}" y="{top + plot_h + 22}" font-size="11" fill="{t["muted"]}" text-anchor="middle">{v}</text>')

    y = top
    for source, size, values in RESULTS:
        cy = y + group_h / 2
        out.append(f'<text x="{left - 14}" y="{cy - 3:.1f}" font-size="12.5" font-weight="600" fill="{t["text"]}" text-anchor="end">{source}</text>')
        out.append(f'<text x="{left - 14}" y="{cy + 12:.1f}" font-size="11" fill="{t["muted"]}" text-anchor="end">{size}</text>')
        for i, (name, key) in enumerate(SERIES):
            v = values[key]
            by = y + i * (bar_h + bar_gap)
            w = max(2.0, x(v) - left)
            r = min(4, w / 2)
            # anchored to the baseline: square start, rounded data end
            out.append(f'<path d="M{left},{by} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} v{bar_h - 2 * r} a{r},{r} 0 0 1 -{r},{r} h-{w - r:.1f} z" '
                       f'fill="{t["series"][i]}"><title>{name} — {source}: {v:.2f} MB/s</title></path>')
            # value labels in text ink (also the required relief for the light-mode aqua's low contrast)
            out.append(f'<text x="{left + w + 6:.1f}" y="{by + bar_h - 2}" font-size="10.5" fill="{t["muted"]}">{v:.1f}</text>')
        y += group_h + group_gap

    out.append(f'<line x1="{left}" y1="{top - 6}" x2="{left}" y2="{top + plot_h + 4}" stroke="{t["muted"]}" stroke-width="1"/>')
    out.append(f'<text x="{W - 20}" y="{H - 10}" font-size="10.5" fill="{t["muted"]}" text-anchor="end">Mean of 3 runs · one home connection · 2026-11-12</text>')
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    for name, theme in THEMES.items():
        with open(os.path.join(ROOT, "assets", f"benchmark-{name}.svg"), "w", encoding="utf-8") as fh:
            fh.write(render(theme))
        print(f"wrote assets/benchmark-{name}.svg")
