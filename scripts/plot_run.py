#!/usr/bin/env python3
"""Ritar före och efter för en kalibreringskörning som SVG (och PNG om rsvg-convert finns).

Läser before.txt, after.txt, colors_before.txt och colors_after.txt i körningens mapp och skriver
report.svg och report.png bredvid dem. Inga beroenden utöver Python.

Användning: scripts/plot_run.py data/runs/<körning>
"""

import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

BEFORE, AFTER = "#eb6834", "#2a78d6"
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
W, PAD_L, PAD_R = 1200, 80, 40


def gray(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        # Vitt saknar gamma, så den kolumnen är valfri.
        m = re.match(r"\s*(\d+)%\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s+([\d.]+))?\s+([\d.]+)\s*$",
                     line)
        if m:
            lv, _, _, x, y, g, de = m.groups()
            rows.append((int(lv), float(x), float(y), float(g) if g else None, float(de)))
    return rows


def colors(path: Path):
    rows = []
    for line in path.read_text().splitlines():
        m = re.match(r"(\S+) (\d+)%\s+.*\s([\d.]+)$", line)
        if m:
            rows.append((f"{m.group(1)} {m.group(2)}", float(m.group(3))))
    return rows


def summary(path: Path):
    m = re.search(r"ΔE00 medel (\d+\.\d+), max (\d+\.\d+)", path.read_text())
    return (float(m.group(1)), float(m.group(2))) if m else None


class Panel:
    def __init__(self, top, height, title, ymin, ymax, yticks, fmt="{:g}"):
        self.top, self.h, self.ymin, self.ymax = top, height, ymin, ymax
        self.x0, self.x1 = PAD_L, W - PAD_R
        self.out = [f'<text x="{PAD_L}" y="{top - 16}" class="h2">{title}</text>']
        for t in yticks:
            y = self.y(t)
            self.out.append(f'<line x1="{self.x0}" x2="{self.x1}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>')
            self.out.append(f'<text x="{self.x0 - 10}" y="{y + 4:.1f}" class="tick" text-anchor="end">'
                            f'{fmt.format(t).replace(".", ",")}</text>')
        self.out.append(f'<line x1="{self.x0}" x2="{self.x1}" y1="{self.y(ymin):.1f}" '
                        f'y2="{self.y(ymin):.1f}" stroke="{AXIS}"/>')

    def y(self, v):
        v = min(max(v, self.ymin), self.ymax)
        return self.top + self.h * (1 - (v - self.ymin) / (self.ymax - self.ymin))

    def ref(self, v, label):
        y = self.y(v)
        self.out.append(f'<line x1="{self.x0}" x2="{self.x1}" y1="{y:.1f}" y2="{y:.1f}" stroke="{INK2}" '
                        f'stroke-dasharray="6 5" stroke-width="1.5"/>')
        self.out.append(f'<text x="{self.x0 + 8}" y="{y - 6:.1f}" class="lbl">{label}</text>')


def line_panel(p: Panel, series, xs, xlabels):
    span = len(xs) - 1
    px = lambda i: p.x0 + 20 + (p.x1 - p.x0 - 40) * i / span
    for i, lab in enumerate(xlabels):
        if lab:
            p.out.append(f'<text x="{px(i):.1f}" y="{p.top + p.h + 22}" class="tick" '
                         f'text-anchor="middle">{lab}</text>')
    for color, vals, name in series:
        pts = [(px(i), p.y(v)) for i, v in enumerate(vals) if v is not None]
        p.out.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round" '
                     f'points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}"/>')
        for a, b in pts:
            p.out.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4.5" fill="{color}" stroke="{SURFACE}" '
                         f'stroke-width="2"/>')
        a, b = pts[-1]
        p.out.append(f'<text x="{a - 10:.1f}" y="{b - 12:.1f}" class="lbl" text-anchor="end">{name}</text>')


def bar_panel(p: Panel, before, after):
    n = len(before)
    slot = (p.x1 - p.x0) / n
    bw = min(22, slot / 2 - 4)
    for i, ((name, b), (_, a)) in enumerate(zip(before, after)):
        cx = p.x0 + slot * (i + 0.5)
        for color, v, dx in ((BEFORE, b, -bw - 1), (AFTER, a, 1)):
            y, base = p.y(v), p.y(0)
            p.out.append(f'<path d="M{cx + dx:.1f},{base:.1f} V{y + 4:.1f} q0,-4 4,-4 H{cx + dx + bw - 4:.1f} '
                         f'q4,0 4,4 V{base:.1f} Z" fill="{color}"/>')
        p.out.append(f'<text x="{cx:.1f}" y="{p.top + p.h + 20}" class="tick" text-anchor="middle">'
                     f'{name.split()[0]}</text>')
        p.out.append(f'<text x="{cx:.1f}" y="{p.top + p.h + 36}" class="tick" text-anchor="middle">'
                     f'{name.split()[1]}</text>')


def main(run: Path) -> Path:
    gb, ga = gray(run / "before.txt"), gray(run / "after.txt")
    cb, ca = colors(run / "colors_before.txt"), colors(run / "colors_after.txt")
    sb, sa = summary(run / "before.txt"), summary(run / "after.txt")
    cmb, cma = summary(run / "colors_before.txt"), summary(run / "colors_after.txt")
    levels = [r[0] for r in ga]
    xl = [f"{lv} %" if lv % 10 == 0 else "" for lv in levels]
    num = lambda v: f"{v:.2f}".replace(".", ",")

    body = []
    head = (f'<text x="{PAD_L}" y="48" class="h1">Kalibrering {run.name[:10]} – före och efter</text>'
            f'<text x="{PAD_L}" y="78" class="sub">Gråskala ΔE00 medel {num(sb[0])} → {num(sa[0])}, '
            f'max {num(sb[1])} → {num(sa[1])} · Färger medel {num(cmb[0])} → {num(cma[0])}, '
            f'max {num(cmb[1])} → {num(cma[1])} · Mål D65, gamma 2,2, BT.709</text>'
            f'<rect x="{PAD_L}" y="96" width="14" height="14" rx="3" fill="{BEFORE}"/>'
            f'<text x="{PAD_L + 22}" y="108" class="lbl">Före</text>'
            f'<rect x="{PAD_L + 80}" y="96" width="14" height="14" rx="3" fill="{AFTER}"/>'
            f'<text x="{PAD_L + 102}" y="108" class="lbl">Efter</text>')

    top1 = 3 * math.ceil(max(r[4] for r in gb + ga) / 3)
    p1 = Panel(170, 260, "Gråskala: färgfel ΔE00 per nivå (lägre är bättre)", 0, top1,
               range(0, top1 + 1, 3))
    p1.ref(1, "ΔE00 1 – knappt synligt")
    line_panel(p1, [(BEFORE, [r[4] for r in gb], "Före"), (AFTER, [r[4] for r in ga], "Efter")], levels, xl)

    low = min(1.8, math.floor(5 * min(r[3] for r in gb + ga if r[3] is not None)) / 5)
    p2 = Panel(520, 260, "Gråskala: effektiv gamma per nivå (mål 2,2)", low, 2.5,
               [round(low + 0.2 * i, 1) for i in range(int((2.5 - low) / 0.2 + 1e-9) + 1)], "{:.1f}")
    p2.ref(2.2, "mål 2,2")
    line_panel(p2, [(BEFORE, [r[3] for r in gb], "Före"), (AFTER, [r[3] for r in ga], "Efter")], levels, xl)

    top3 = 2 * math.ceil(max(v for _, v in cb + ca) / 2)
    p3 = Panel(870, 260, "Färger: ΔE00 per färg och nivå mot BT.709", 0, top3, range(0, top3 + 1, 2))
    p3.ref(3, "ΔE00 3")
    bar_panel(p3, cb, ca)

    for p in (p1, p2, p3):
        body += p.out
    h = 1200
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}">
<style>
text {{ font-family: "Inter", "DejaVu Sans", sans-serif; }}
.h1 {{ font-size: 28px; font-weight: 600; fill: {INK}; }}
.h2 {{ font-size: 19px; font-weight: 600; fill: {INK}; }}
.sub {{ font-size: 16px; fill: {INK2}; }}
.lbl {{ font-size: 14px; fill: {INK2}; }}
.tick {{ font-size: 13px; fill: {MUTED}; }}
</style>
<rect width="100%" height="100%" fill="{SURFACE}"/>
{head}
{chr(10).join(body)}
</svg>
'''
    out = run / "report.svg"
    out.write_text(svg)
    if shutil.which("rsvg-convert"):
        png = run / "report.png"
        subprocess.run(["rsvg-convert", "-o", str(png), str(out)], check=True)
        return png
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(main(Path(sys.argv[1])))
