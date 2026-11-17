"""Simulerad TV och mätare för tester av kalibreringslooparna.

Modellen bygger på mätningarna 2026-11-15 i docs/HARDWARE.md. Den är inte exakt, men har samma
egenskaper som looparna måste klara: ojämna steg i bakgrundsljuset, gain som verkar först när
läget laddas om och har tak vid 1024, gammaförval som ligger över sitt namn, en topp som trycks
ihop och flerpunkts vitbalans som bara verkar på sin egen nivå.
"""

import bisect
import math
import random

from .color import Reading, xyy_to_xyz

# Vitt på 10 % fönster per Backlight, med de ojämna stegen kring 28–30.
BACKLIGHT_TABLE = [(0, 157.2), (10, 225.2), (20, 297.8), (25, 324.2), (28, 347.3), (29, 347.0),
                   (30, 357.6), (31, 364.3), (32, 369.0), (35, 388.9), (40, 419.4), (50, 481.2),
                   (75, 622.1), (100, 754.5)]
# Uppmätt effektiv gamma per förval, och hur mycket toppen ligger över kurvan.
GAMMA = {"Gamma18": 1.90, "Gamma20": 2.11, "Gamma22": 2.33, "Gamma24": 2.55, "Gamma26": 2.75}
TOP = [(0.75, 1.0), (0.80, 1.02), (0.85, 1.037), (0.90, 1.08), (0.95, 1.055), (1.0, 1.0)]
# Panelens primärer (uppmätta rutor) och vitt med all gain på 1024.
PRIMARIES = {"Red": (0.632, 0.344), "Green": (0.314, 0.5875), "Blue": (0.156, 0.0577)}
WHITE_1024 = (0.2944, 0.3000)
PRESETS = {"Warm": (1036, 1024, 976), "Standard": (980, 1000, 1024), "Cool": (855, 919, 1060)}
GAIN_CAP = {"Red": 1036, "Green": 1024, "Blue": 1024}
GAIN_EXPONENT = 2.6          # gain verkar före gammakurvan; uppmätt 1,8–3,4 beroende på kanal och nivå
POINT_STEP = 0.016           # relativ ändring av kanalen per steg i flerpunkts vitbalansen
# Grått på 65–95 % ligger högre i y än vitt (uppmätt +0,004 före och efter kalibrering).
TOP_TINT_Y = [(0.60, 0.0), (0.65, 0.004), (0.95, 0.004), (1.0, 0.0)]
# Lokaldämpningen släcker zonen helt under cirka 0,2–0,3 cd/m², i alla lägen utom Off
# (5 % blev 0 vid Backlight=8 i High, Middle och Low). Att den också trycker ner 10–20 % och
# lyfter svart till 0,04 cd/m² när den är av är inte med.
LD_BLACKOUT_Y = 0.25
CHANNELS = ("Red", "Green", "Blue")


def _interp(table, x):
    xs = [p[0] for p in table]
    if x <= xs[0]:
        return table[0][1]
    if x >= xs[-1]:
        return table[-1][1]
    i = bisect.bisect_right(xs, x)
    (x0, y0), (x1, y1) = table[i - 1], table[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _solve3(m, v):
    """Löser m·u = v med Cramers regel (3×3)."""
    def det(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    d = det(m)
    out = []
    for col in range(3):
        mc = [row[:] for row in m]
        for r in range(3):
            mc[r][col] = v[r]
        out.append(det(mc) / d)
    return out


def _channel_shares():
    """Andelen av vitts Y som varje kanal står för, så att lika styrning ger WHITE_1024."""
    cols = [xyy_to_xyz(*PRIMARIES[c], 1.0) for c in CHANNELS]
    m = [[cols[c][r] for c in range(3)] for r in range(3)]
    return dict(zip(CHANNELS, _solve3(m, xyy_to_xyz(*WHITE_1024, 1.0))))


SHARES = _channel_shares()


class SimTV:
    """Samma gränssnitt som tvcal.tv.TV för get och set, plus show_gray för mönster."""

    def __init__(self, backlight=30, gamma="Gamma22", mode="Warm"):
        self.db = {"Backlight": str(backlight), "Gamma": gamma, "Color_Temperature": mode,
                   "PQ_WB_11_Point_enabled": "Off", "LD_MODE": "High", "Global_Dimming": "On",
                   "Local_Contrast": "Middle"}
        for name, gains in PRESETS.items():
            for c, g in zip(CHANNELS, gains):
                self.db[f"Color_Temperature_{name}_{c}_Gain"] = str(g)
        for a in "HSY":
            for f in "RGBCMYF":
                self.db[f"COLORTUNER_{a}_{f}"] = "50"
        for c in "RGB":
            self.db[f"COLORTUNER_{c}_GAIN"] = self.db[f"COLORTUNER_{c}_OFFSET"] = "50"
        self.db.update({"COLORTUNER_SWITCH": "Off", "Color_space": "Auto", "Gamut_Mapping": "Disable"})
        for c in CHANNELS:
            self.db[f"Color_Temperature_{c}_Gain"] = "1024"
            for i in range(12):
                self.db[f"PQ_WB_11_Point_{i}_{c}"] = "50"
        self.hal_gain = dict(zip(CHANNELS, PRESETS[mode]))
        self.rgb = (1.0, 1.0, 1.0)
        self.writes = 0

    def connect(self):
        pass

    def get(self, key):
        return self.db.get(key, "<saknas>")

    def set(self, key, value):
        value = str(value)
        if key not in self.db:
            raise KeyError(key)
        self.db[key] = value
        self.writes += 1
        if key == "Color_Temperature":
            # Byte av läge laddar förinställningen till HAL:en.
            self.hal_gain = {c: int(self.db[f"Color_Temperature_{value}_{c}_Gain"]) for c in CHANNELS}
        elif key.startswith("Color_Temperature_") and key.endswith("_Gain") and key.count("_") == 3:
            # Den aktiva nyckeln går direkt till HAL:en.
            self.hal_gain[key.split("_")[2]] = int(value)

    def show_gray(self, level):
        self.rgb = (level, level, level)

    def show_rgb(self, rgb):
        self.rgb = tuple(rgb)

    def home(self):
        pass

    def render(self) -> Reading:
        white = _interp(BACKLIGHT_TABLE, int(self.db["Backlight"]))
        gamma = GAMMA[self.db["Gamma"]]
        enabled = self.db["PQ_WB_11_Point_enabled"] == "On"
        X = Y = Z = 0.0
        for c, level in zip(CHANNELS, self.rgb):
            if level <= 0:
                continue
            gain = min(self.hal_gain[c], GAIN_CAP[c]) / 1024
            drive = SHARES[c] * gain ** GAIN_EXPONENT
            point = round(level * 20) - 1 if enabled else -1
            if 0 <= point < 12:
                drive *= max(0.0, 1 + POINT_STEP * (int(self.db[f"PQ_WB_11_Point_{point}_{c}"]) - 50))
            cx, cy, cz = xyy_to_xyz(*PRIMARIES[c], drive * white * level ** gamma * _interp(TOP, level))
            X, Y, Z = X + cx, Y + cy, Z + cz
        if self.db["LD_MODE"] != "Off" and Y < LD_BLACKOUT_Y:
            Y = 0.0
        if Y <= 0:
            return Reading(0.0, 1 / 3, 1 / 3)
        s = X + Y + Z
        tint = _interp(TOP_TINT_Y, self.rgb[1]) if len(set(self.rgb)) == 1 else 0.0
        return self._tuner(Reading(Y, X / s, Y / s + tint))

    def _tuner(self, r: Reading) -> Reading:
        """Färghanteringen, anpassad till svepen av rött på TV:n (docs/HARDWARE.md).

        Verkar bara på rena primär- och sekundärfärger, var och en med sina egna reglage.
        Knyck vid 50: under 50 sänker mättnad och ljus luminansen och nyansen drar färgen
        inåt och medurs; över 50 gör mättnaden ingenting, nyansen sänker luminansen och
        ljuset höjer den men bleker färgen.
        """
        if self.db["COLORTUNER_SWITCH"] != "On":
            return r
        on = tuple(int(c > 0) for c in self.rgb)
        name = {(1, 0, 0): "R", (0, 1, 0): "G", (0, 0, 1): "B", (0, 1, 1): "C",
                (1, 0, 1): "M", (1, 1, 0): "Y"}.get(on)
        if name is None:
            return r
        h, sat, lum = (int(self.db[f"COLORTUNER_{a}_{name}"]) - 50 for a in "HSY")
        Y, radial, angle = r.Y, 1.0, 0.0
        if sat < 0:
            Y *= 1 + 0.035 * sat
            radial *= 1 + 0.0012 * sat
        if h < 0:
            angle -= 0.021 * h * h
            radial *= 1 - 0.00073 * h * h
        elif h > 0:
            Y *= 1 - 0.0016 * h * h
        if lum < 0:
            Y *= 1 + 0.025 * lum
        elif lum > 0:
            Y *= 1 + 0.0042 * lum
            radial *= 1 - 0.003 * lum
        wx, wy = WHITE_1024
        dx, dy = (r.x - wx) * radial, (r.y - wy) * radial
        a = math.radians(angle)
        dx, dy = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
        return Reading(max(0.0, Y), wx + dx, wy + dy)


class SimMeter:
    def __init__(self, tv: SimTV, noise: float = 0.0, seed: int = 1):
        self.tv = tv
        self.noise = noise
        self.rng = random.Random(seed)
        self.count = 0

    def measure(self) -> Reading:
        self.count += 1
        r = self.tv.render()
        if not self.noise:
            return r
        n = lambda s: self.rng.gauss(0, s)
        return Reading(r.Y * (1 + n(self.noise)), r.x + n(self.noise * 0.05), r.y + n(self.noise * 0.05))


# HDR10-läget, efter proven 2026-11-17: kvoten mätt/PQ per nivå, panelens primärer på
# HDR-signal, vitt med Warm 1036/1024/976 och punkternas verkan kring sina nivåer.
HDR_TONE = [(0, 0.4), (1, 1.44), (5, 4.95), (10, 9.2), (20, 20.0), (50, 50.7), (100, 99.1),
            (203, 199.6), (400, 403.0), (600, 580.0), (700, 627.0), (800, 657.0), (1000, 696.0),
            (2000, 740.0), (10000, 740.0)]
HDR_PRIMARIES = {"Red": (0.6528, 0.3049), "Green": (0.2695, 0.6641), "Blue": (0.1562, 0.0493)}
HDR_WHITE = (0.2995, 0.3095)
HDR_GAIN_EXPONENT = 2.3     # blått −96 gav x +0,015, y +0,026 på alla nivåer
HDR_POINT_STEP = 0.010       # relativ ändring av kanalen per steg vid punktens topp
HDR_POINT_WIDTH = 0.4        # punktens verkan går till noll ln(L/Lᵢ) = ±0,4 bort


def _hdr_shares():
    cols = [xyy_to_xyz(*HDR_PRIMARIES[c], 1.0) for c in CHANNELS]
    m = [[cols[c][r] for c in range(3)] for r in range(3)]
    return dict(zip(CHANNELS, _solve3(m, xyy_to_xyz(*HDR_WHITE, 1.0))))


HDR_SHARES = _hdr_shares()


class SimHDRTV(SimTV):
    """HDR10-läget: samma nycklar som SimTV men egna startvärden och en PQ-modell."""

    def __init__(self):
        super().__init__(backlight=100, mode="Warm")
        self.db.update({"LD_MODE": "Off", "Local_Contrast": "Off", "Global_Dimming": "Off"})
        self.nits = 100.0
        self.require_hdr = None

    def show_nits(self, nits):
        self.nits = nits

    def show_video(self, nits, settle=0):
        """I testerna ersätts mönsterfilen av sin luminans."""
        self.nits = nits

    def render(self) -> Reading:
        from .hdrcal import point_nits
        Y0 = _interp(HDR_TONE, self.nits)
        enabled = self.db["PQ_WB_11_Point_enabled"] == "On"
        X = Y = Z = 0.0
        for c in CHANNELS:
            drive = HDR_SHARES[c] * (self.hal_gain[c] / PRESETS["Warm"][CHANNELS.index(c)]) ** HDR_GAIN_EXPONENT
            if enabled:
                for i in range(12):
                    w = max(0.0, 1 - abs(math.log(max(self.nits, 1e-3) / point_nits(i))) / HDR_POINT_WIDTH)
                    drive *= 1 + HDR_POINT_STEP * w * (int(self.db[f"PQ_WB_11_Point_{i}_{c}"]) - 50)
            cx, cy, cz = xyy_to_xyz(*HDR_PRIMARIES[c], drive * Y0)
            X, Y, Z = X + cx, Y + cy, Z + cz
        s = X + Y + Z
        return Reading(Y, X / s, Y / s)
