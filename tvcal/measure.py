"""Mätning av gråskalan och rapport mot målet."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from . import color
from .color import Reading
from .patterns import gray_code


@dataclass
class GrayRow:
    level: float          # signalnivå 0–1, efter avrundning till 8 bitar
    Y: float
    x: float
    y: float
    target_Y: float
    delta_e: float
    gamma: float | None   # effektiv gamma; None för vitt och svart


def default_levels(step: int = 5) -> list[float]:
    return [p / 100 for p in range(step, 101, step)]


def grayscale(show: Callable[[float], None], measure: Callable[[], Reading],
              levels: list[float], gamma: float = 2.2) -> list[GrayRow]:
    """Mäter varje nivå och jämför med målet relativt uppmätt vitt.

    Vitt mäts först, så att målet för övriga nivåer kan räknas ut. Målets färgpunkt är D65.
    """
    levels = sorted({gray_code(lv) / 255 for lv in levels})
    if levels[-1] != 1.0:
        levels.append(1.0)
    show(1.0)
    white = measure()
    readings = {1.0: white}
    for level in levels[:-1]:
        show(level)
        readings[level] = measure()

    rows = []
    for level in levels:
        r = readings[level]
        target = color.gray_target(level, white.Y, gamma)
        g = color.effective_gamma(r.Y, white.Y, level) if 0 < level < 1 and r.Y > 0 else None
        rows.append(GrayRow(level, r.Y, r.x, r.y, target.Y,
                            color.gray_delta_e(r, target, white.Y), g))
    return rows


def summary(rows: list[GrayRow]) -> dict:
    des = [r.delta_e for r in rows]
    return {"mean_delta_e": sum(des) / len(des), "max_delta_e": max(des),
            "white_Y": rows[-1].Y, "white_x": rows[-1].x, "white_y": rows[-1].y}


def format_report(rows: list[GrayRow], title: str) -> str:
    lines = [title, "",
             f"{'nivå':>5} {'Y cd/m²':>9} {'mål Y':>9} {'x':>7} {'y':>7} {'gamma':>6} {'ΔE00':>6}"]
    for r in rows:
        g = f"{r.gamma:6.2f}" if r.gamma is not None else f"{'':6}"
        lines.append(f"{r.level * 100:4.0f}% {r.Y:9.3f} {r.target_Y:9.3f} {r.x:7.4f} {r.y:7.4f}"
                     f" {g} {r.delta_e:6.2f}")
    s = summary(rows)
    lines += ["", f"ΔE00 medel {s['mean_delta_e']:.2f}, max {s['max_delta_e']:.2f}. "
              f"Mål: D65, gamma 2,2 relativt uppmätt vitt."]
    return "\n".join(lines)


def save(rows: list[GrayRow], directory: Path, name: str, meta: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(json.dumps(
        {"meta": meta, "summary": summary(rows), "rows": [asdict(r) for r in rows]},
        indent=2, ensure_ascii=False))
    path = directory / f"{name}.txt"
    path.write_text(format_report(rows, meta.get("title", name)) + "\n")
    return path


# Färgrutor: 100 % och 75 % av primärer och sekundärer.
COLOR_PATCHES = {
    f"{name} {int(level * 100)}%": tuple(level * c for c in rgb)
    for level in (1.0, 0.75)
    for name, rgb in [("Röd", (1, 0, 0)), ("Grön", (0, 1, 0)), ("Blå", (0, 0, 1)),
                      ("Cyan", (0, 1, 1)), ("Magenta", (1, 0, 1)), ("Gul", (1, 1, 0))]
}


@dataclass
class ColorRow:
    name: str
    rgb: tuple
    Y: float
    x: float
    y: float
    target_Y: float
    target_x: float
    target_y: float
    delta_e: float


def colors(show_rgb: Callable, measure: Callable[[], Reading], white_y: float,
           patches: dict = COLOR_PATCHES, gamma: float = 2.2) -> list[ColorRow]:
    """Mäter färgrutorna mot BT.709 med gamma och vitt white_y (D65)."""
    rows = []
    for name, rgb in patches.items():
        show_rgb(rgb)
        r = measure()
        t = color.rgb_target(rgb, white_y, gamma)
        rows.append(ColorRow(name, rgb, r.Y, r.x, r.y, t.Y, t.x, t.y,
                             color.gray_delta_e(r, t, white_y)))
    return rows


def format_colors(rows: list[ColorRow], title: str) -> str:
    lines = [title, "", f"{'färg':12} {'Y':>8} {'mål Y':>8} {'x':>7} {'mål x':>7} {'y':>7} {'mål y':>7} {'ΔE00':>6}"]
    for r in rows:
        lines.append(f"{r.name:12} {r.Y:8.2f} {r.target_Y:8.2f} {r.x:7.4f} {r.target_x:7.4f}"
                     f" {r.y:7.4f} {r.target_y:7.4f} {r.delta_e:6.2f}")
    des = [r.delta_e for r in rows]
    lines += ["", f"ΔE00 medel {sum(des) / len(des):.2f}, max {max(des):.2f}. Mål: BT.709, D65, gamma 2,2."]
    return "\n".join(lines)
