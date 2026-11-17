"""HDR10-kalibrering: mätning mot PQ och steg för vitpunkt och flerpunkts vitbalans.

Bygger på proven 2026-11-17 (docs/HARDWARE.md, "HDR10 från provappen"):
- TV:n byter till HDR10 för provappens HEVC-mönster och har egna värden där; SDR rörs inte.
- Kurvan följer PQ inom cirka ±4 % upp till 600 cd/m² och avrundas mot cirka 740 cd/m².
- 2-punkts gain (förinställningen Warm, omladdad) flyttar vitpunkten lika mycket på alla nivåer.
- Punkt i i flerpunkts vitbalansen verkar kring POINT_PEAK × (0,05·(i+1))^2,2 cd/m², alltså
  1–244 cd/m², och slår igenom direkt när PQ_WB_11_Point_enabled=On.

Mönstret startas om före varje mätning och mäts två gånger: direkt efter att provappen legat
över videon gav samma mönster ibland en annan färgpunkt (x +0,004, y −0,005), som höll i sig
tills videon startades om.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from . import calibrate
from .color import D65, Reading
from .hdr import delta_e_itp

POINT_PEAK = 735.0           # cd/m², anpassat till var punkt 5 och 9 verkar mest (52 och 165)
WHITE_NITS = 400.0           # nivån där 2-punkts gain ställs: över punkterna, under avrundningen
LEVELS = [1, 2.5, 5, 10, 20, 35, 50, 75, 100, 150, 203, 300, 400, 500, 600, 800, 1000, 4000]
SUMMARY_RANGE = (5, 600)     # där TV:n följer PQ; under 5 lyfter svart, över 600 avrundas kurvan
REF_WHITE = 203.0            # HDR-referensvitt; krävs av punktlösaren men används inte med ΔE ITP
LOW_POINT_NITS = 3.0         # under detta ställs bara färgpunkten; svart (0,4 cd/m²) lyfter nivån


# Nycklar som HDR-kalibreringen kan skriva, i återställningsordning (läget sist).
KEYS = (["LD_MODE", "Local_Contrast"]
        + [f"Color_Temperature_Warm_{c}_Gain" for c in calibrate.CHANNELS]
        + [f"PQ_WB_11_Point_{i}_{c}" for i in range(12) for c in calibrate.CHANNELS]
        + ["PQ_WB_11_Point_enabled", "Color_Temperature"])


def point_nits(index: int) -> float:
    return POINT_PEAK * (0.05 * (index + 1)) ** 2.2


class Screen:
    """Visar HDR-mönster och mäter dem. show(nits) visar ett grått på nits cd/m².

    measure() startar om det senast visade mönstret före varje avläsning och kräver att två
    avläsningar stämmer (färgpunkt inom tol_xy, luminans inom tol_y); en tredje tas annars.
    """

    def __init__(self, show: Callable[[float], None], read: Callable[[], Reading],
                 tol_xy: float = 0.0015, tol_y: float = 0.02):
        self._show, self._read = show, read
        self.tol_xy, self.tol_y = tol_xy, tol_y
        self.current: float | None = None

    def show(self, nits: float) -> None:
        self.current = nits
        self._show(nits)

    def _fresh(self) -> Reading:
        self._show(self.current)
        return self._read()

    def _close(self, a: Reading, b: Reading) -> bool:
        return (abs(a.x - b.x) <= self.tol_xy and abs(a.y - b.y) <= self.tol_xy
                and abs(a.Y - b.Y) <= self.tol_y * max(a.Y, b.Y, 0.05))

    def measure(self) -> Reading:
        readings = [self._fresh(), self._fresh()]
        if not self._close(*readings):
            readings.append(self._fresh())
            pairs = [(a, b) for i, a in enumerate(readings) for b in readings[i + 1:]]
            close = [p for p in pairs if self._close(*p)]
            if not close:
                from .meter import MeterError
                raise MeterError(f"tre avläsningar av {self.current} cd/m² stämmer inte: {readings}")
            readings = list(close[0])
        return Reading(*(sum(v) / 2 for v in zip(*readings)))


@dataclass
class HdrRow:
    nits: float          # målets luminans (PQ)
    Y: float
    x: float
    y: float
    delta_itp: float


def grayscale(screen: Screen, levels=LEVELS) -> list[HdrRow]:
    rows = []
    for nits in levels:
        screen.show(nits)
        r = screen.measure()
        rows.append(HdrRow(nits, r.Y, r.x, r.y, delta_e_itp(r, Reading(nits, *D65))))
    return rows


def summary(rows: list[HdrRow]) -> dict:
    lo, hi = SUMMARY_RANGE
    des = [r.delta_itp for r in rows if lo <= r.nits <= hi]
    return {"mean_itp": sum(des) / len(des), "max_itp": max(des),
            "peak_Y": max(r.Y for r in rows)}


def format_report(rows: list[HdrRow], title: str) -> str:
    lines = [title, "", f"{'mål':>8} {'Y cd/m²':>9} {'kvot':>6} {'x':>7} {'y':>7} {'ΔE ITP':>7}"]
    for r in rows:
        mark = "" if SUMMARY_RANGE[0] <= r.nits <= SUMMARY_RANGE[1] else "  (utanför)"
        lines.append(f"{r.nits:8.1f} {r.Y:9.3f} {r.Y / r.nits:6.3f} {r.x:7.4f} {r.y:7.4f} "
                     f"{r.delta_itp:7.2f}{mark}")
    s = summary(rows)
    lines += ["", f"ΔE ITP medel {s['mean_itp']:.2f}, max {s['max_itp']:.2f} över "
              f"{SUMMARY_RANGE[0]}–{SUMMARY_RANGE[1]} cd/m²; topp {s['peak_Y']:.0f} cd/m². "
              "Mål: PQ (ST 2084), D65. 1 ≈ precis märkbart."]
    return "\n".join(lines)


def save(rows: list[HdrRow], directory: Path, name: str, meta: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(json.dumps(
        {**meta, "rows": [asdict(r) for r in rows], "summary": summary(rows)}, indent=1,
        ensure_ascii=False))
    path = directory / f"{name}.txt"
    path.write_text(format_report(rows, meta.get("title", name)) + "\n")
    return path


def whitepoint(tv, screen: Screen, white_nits: float = WHITE_NITS) -> calibrate.WhiteResult:
    """2-punkts gain i förinställningen Warm, ställd på white_nits."""
    return calibrate.whitepoint(tv, lambda _level: screen.show(white_nits), screen.measure)


@dataclass
class PointResult:
    index: int
    nits: float
    values: dict
    reading: Reading
    target: Reading
    delta_itp: float
    measurements: int


def multipoint(tv, screen: Screen, indices=range(12), tol_de: float = 1.0,
               log=None, attempts: int = 2) -> list[PointResult]:
    """Ställer punkterna en i taget mot PQ och D65 på sin egen nivå, tills ΔE ITP ≤ tol_de."""
    tv.set("PQ_WB_11_Point_enabled", "On")
    results = []
    for i in indices:
        nits = point_nits(i)
        screen.show(nits)
        target_y = nits if nits >= LOW_POINT_NITS else screen.measure().Y
        target = Reading(target_y, *D65)
        count = 0
        for _ in range(attempts):
            # En avvikande mätning under provstegen kan ge fel riktning; lösaren behåller då
            # utgångsläget. Ett nytt försök från bästa läget räckte för punkt 1, 7 och 9
            # 2026-11-17, som inte rörde sig under hela körningen.
            vals, best, de, n = calibrate.solve_three(
                tv, {c: f"PQ_WB_11_Point_{i}_{c}" for c in calibrate.CHANNELS}, screen.measure,
                target, REF_WHITE, D65, tol_de, metric=delta_e_itp)
            count += n
            if de <= tol_de:
                break
        res = PointResult(i, nits, vals, best, target, delta_e_itp(best, target), count)
        if log:
            log(res)
        results.append(res)
    return results
