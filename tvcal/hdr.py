"""HDR10: PQ-kurvan (SMPTE ST 2084) och 10-bitars kodvärden i BT.2020 för mönstren.

Mönstren anges i absolut luminans (cd/m²) per kanal i linjärt BT.2020-RGB. Kodvärdena räknas
här och inte i skriptet, så att räkningen går att testa.
"""

M1, M2 = 2610 / 16384, 2523 / 4096 * 128
C1, C2, C3 = 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32
PEAK = 10000.0

# BT.2020 med konstant luminans avstängd (ncl): luma-vikter.
KR, KB = 0.2627, 0.0593
KG = 1 - KR - KB

# P3-D65-primärer uttryckta i linjärt BT.2020-RGB (kolumner R, G, B i P3).
P3_IN_BT2020 = ((0.7538, 0.1986, 0.0476),
                (0.0457, 0.9418, 0.0125),
                (-0.0012, 0.0176, 0.9836))

# BT.2020-primärer med D65, linjärt RGB → XYZ (Y för vitt = 1).
BT2020_TO_XYZ = ((0.6370, 0.1446, 0.1689),
                 (0.2627, 0.6780, 0.0593),
                 (0.0000, 0.0281, 1.0610))


def pq_encode(nits: float) -> float:
    """Luminans i cd/m² → PQ-signal 0–1."""
    y = max(0.0, nits) / PEAK
    p = y ** M1
    return ((C1 + C2 * p) / (1 + C3 * p)) ** M2


def pq_decode(signal: float) -> float:
    """PQ-signal 0–1 → luminans i cd/m²."""
    p = max(0.0, signal) ** (1 / M2)
    return PEAK * (max(p - C1, 0.0) / (C2 - C3 * p)) ** (1 / M1)


def limited(v: float, chroma: bool = False) -> int:
    """Signal 0–1 (luma) eller −0,5–0,5 (krominans) → 10-bitars kod i begränsat omfång."""
    if chroma:
        return min(1023, max(0, round(512 + 896 * v)))
    return min(1023, max(0, round(64 + 876 * v)))


def code_to_nits(code: int) -> float:
    """10-bitars lumakod i begränsat omfång → luminans för ett grått med den koden."""
    return pq_decode((code - 64) / 876)


def ycbcr_codes(rgb_nits) -> tuple[int, int, int]:
    """Linjärt BT.2020-RGB i cd/m² → (Y', Cb, Cr) som 10-bitarskoder."""
    r, g, b = (pq_encode(c) for c in rgb_nits)
    y = KR * r + KG * g + KB * b
    cb = (b - y) / (2 * (1 - KB))
    cr = (r - y) / (2 * (1 - KR))
    return limited(y), limited(cb, True), limited(cr, True)


def p3_primary(index: int, white_nits: float) -> tuple[float, float, float]:
    """P3-primär nummer index (0 R, 1 G, 2 B) som BT.2020-RGB: primärens andel av ett P3-vitt
    på white_nits, som en färgruta på 100 % i SDR.

    Små negativa komponenter (under 0,2 %) klipps till noll; de ryms inte i signalen.
    """
    return tuple(white_nits * max(0.0, row[index]) for row in P3_IN_BT2020)


def rgb_luminance(rgb) -> float:
    return sum(w * c for w, c in zip(BT2020_TO_XYZ[1], rgb))


def rgb_xy(rgb) -> tuple[float, float]:
    """Färgpunkten för linjärt BT.2020-RGB."""
    X, Y, Z = (sum(m * c for m, c in zip(row, rgb)) for row in BT2020_TO_XYZ)
    s = X + Y + Z
    return (X / s, Y / s)


# XYZ (D65, absolut) → LMS för ICtCp, ITU-R BT.2100.
XYZ_TO_LMS = ((0.3592, 0.6976, -0.0358),
              (-0.1922, 1.1004, 0.0755),
              (0.0070, 0.0749, 0.8434))


def ictcp(X: float, Y: float, Z: float) -> tuple[float, float, float]:
    """XYZ i cd/m² → ICtCp (PQ)."""
    l, m, s = (pq_encode(sum(a * v for a, v in zip(row, (X, Y, Z)))) for row in XYZ_TO_LMS)
    return (0.5 * l + 0.5 * m,
            (6610 * l - 13613 * m + 7003 * s) / 4096,
            (17933 * l - 17390 * m - 543 * s) / 4096)


def delta_e_itp(a, b) -> float:
    """ΔE ITP (ITU-R BT.2124) mellan två Reading (Y i cd/m², x, y). 1 ≈ precis märkbart."""
    from .color import xyy_to_xyz
    i1, t1, p1 = ictcp(*xyy_to_xyz(a.x, a.y, a.Y))
    i2, t2, p2 = ictcp(*xyy_to_xyz(b.x, b.y, b.Y))
    return 720 * ((i1 - i2) ** 2 + (0.5 * (t1 - t2)) ** 2 + (p1 - p2) ** 2) ** 0.5
