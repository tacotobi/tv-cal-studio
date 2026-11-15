"""Färgräkning för gråskalekalibreringen: omräkningar, ΔE2000 och målvärden."""

import math
from typing import NamedTuple

D65 = (0.3127, 0.3290)


class Reading(NamedTuple):
    """En mätning eller ett målvärde: luminans i cd/m² och färgpunkt."""
    Y: float
    x: float
    y: float


def xyy_to_xyz(x: float, y: float, Y: float) -> tuple[float, float, float]:
    if y <= 0:
        return (0.0, 0.0, 0.0)
    return (x * Y / y, Y, (1.0 - x - y) * Y / y)


def xyz_to_lab(xyz, white_xyz) -> tuple[float, float, float]:
    eps, kappa = 216 / 24389, 24389 / 27

    def f(t: float) -> float:
        return t ** (1 / 3) if t > eps else (kappa * t + 16) / 116

    fx, fy, fz = (f(v / w) for v, w in zip(xyz, white_xyz))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e2000(lab1, lab2) -> float:
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C_mean = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    G = 0.5 * (1 - math.sqrt(C_mean ** 7 / (C_mean ** 7 + 25 ** 7)))
    a1p, a2p = a1 * (1 + G), a2 * (1 + G)
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if C1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if C2p else 0.0

    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2)

    Lp_mean = (L1 + L2) / 2
    Cp_mean = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hp_mean = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_mean = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hp_mean = (h1p + h2p + 360) / 2
    else:
        hp_mean = (h1p + h2p - 360) / 2

    T = (1 - 0.17 * math.cos(math.radians(hp_mean - 30))
         + 0.24 * math.cos(math.radians(2 * hp_mean))
         + 0.32 * math.cos(math.radians(3 * hp_mean + 6))
         - 0.20 * math.cos(math.radians(4 * hp_mean - 63)))
    d_theta = 30 * math.exp(-(((hp_mean - 275) / 25) ** 2))
    R_C = 2 * math.sqrt(Cp_mean ** 7 / (Cp_mean ** 7 + 25 ** 7))
    S_L = 1 + 0.015 * (Lp_mean - 50) ** 2 / math.sqrt(20 + (Lp_mean - 50) ** 2)
    S_C = 1 + 0.045 * Cp_mean
    S_H = 1 + 0.015 * Cp_mean * T
    R_T = -math.sin(math.radians(2 * d_theta)) * R_C

    return math.sqrt((dLp / S_L) ** 2 + (dCp / S_C) ** 2 + (dHp / S_H) ** 2
                     + R_T * (dCp / S_C) * (dHp / S_H))


def gray_target(level: float, white_y: float, gamma: float = 2.2, white_xy=D65) -> Reading:
    """Målet för en grånivå (0–1 av full signal): ren potensfunktion och samma färgpunkt som vitt."""
    if not 0.0 <= level <= 1.0:
        raise ValueError(f"nivån ska vara 0–1, fick {level}")
    return Reading(white_y * level ** gamma, *white_xy)


def gray_delta_e(measured: Reading, target: Reading, white_y: float, white_xy=D65) -> float:
    """ΔE2000 mellan mätning och mål, med målets vitt som referens för Lab."""
    white = xyy_to_xyz(*white_xy, white_y)
    return delta_e2000(xyz_to_lab(xyy_to_xyz(measured.x, measured.y, measured.Y), white),
                       xyz_to_lab(xyy_to_xyz(target.x, target.y, target.Y), white))


def effective_gamma(y: float, white_y: float, level: float) -> float:
    """Den gamma som ger luminansen y vid nivån level, relativt vitt."""
    return math.log(y / white_y) / math.log(level)


# BT.709/sRGB-primärer med D65, linjärt RGB → XYZ (Y för vitt = 1).
BT709_TO_XYZ = ((0.4124, 0.3576, 0.1805),
                (0.2126, 0.7152, 0.0722),
                (0.0193, 0.1192, 0.9505))


def rgb_target(rgb, white_y: float, gamma: float = 2.2) -> Reading:
    """Målet för en färg med signalvärden rgb (0–1) i BT.709, gamma och vitt white_y."""
    lin = [c ** gamma for c in rgb]
    X, Y, Z = (white_y * sum(m * c for m, c in zip(row, lin)) for row in BT709_TO_XYZ)
    s = X + Y + Z
    return Reading(Y, X / s, Y / s) if s > 0 else Reading(0.0, *D65)
