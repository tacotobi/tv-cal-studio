"""Kalibreringsstegen. Varje steg tar tv (get/set), show(nivå) och measure() som argument,
så att samma kod körs mot TV:n och mot simuleringen i tvcal.sim."""

from dataclasses import dataclass, field

BACKLIGHT_RANGE = (0, 100)
BACKLIGHT_SLOPE = 6.0      # cd/m² per steg på vitt, uppmätt medel 0–100


@dataclass
class StepResult:
    value: int
    Y: float
    reached: bool
    history: list = field(default_factory=list)   # (värde, Y) i mätordning


def backlight(tv, show, measure, target_y: float, tol: float = 0.02, max_steps: int = 8) -> StepResult:
    """Ställer Backlight så att vitt hamnar närmast target_y.

    Sekantsökning från nuvarande värde, sedan grannarna till det bästa värdet: stegen är
    ojämna (kring 28–30 ligger 29 ibland över 30), så det närmaste uppmätta värdet väljs,
    inte det senaste. Mål utanför intervallet ger ändpunkten och reached=False.
    """
    lo, hi = BACKLIGHT_RANGE
    show(1.0)
    seen: dict[int, float] = {}

    def at(value: int) -> float:
        if value not in seen:
            tv.set("Backlight", value)
            seen[value] = measure().Y
            history.append((value, seen[value]))
        return seen[value]

    history: list = []
    b = int(tv.get("Backlight"))
    y = at(b)
    slope = BACKLIGHT_SLOPE
    for _ in range(max_steps):
        nxt = max(lo, min(hi, b + round((target_y - y) / slope)))
        if nxt == b or nxt in seen:
            break
        y_next = at(nxt)
        if y_next != y:
            slope = max(0.5, (y_next - y) / (nxt - b))
        b, y = nxt, y_next

    best = min(seen, key=lambda v: abs(seen[v] - target_y))
    for n in (best - 1, best + 1):
        if lo <= n <= hi:
            at(n)
    best = min(seen, key=lambda v: abs(seen[v] - target_y))
    if history[-1][0] != best:
        tv.set("Backlight", best)
    y = seen[best]
    # Nåbart om felet är högst tol eller mindre än ett halvt steg åt något håll.
    neighbours = [seen[n] for n in (best - 1, best + 1) if n in seen]
    half_step = max((abs(n - y) for n in neighbours), default=0) / 2
    reached = abs(y - target_y) <= max(tol * target_y, half_step)
    return StepResult(best, y, reached, history)


CHANNELS = ("Red", "Green", "Blue")
GAIN_CAP = {"Red": 1036, "Green": 1024, "Blue": 1024}   # uppmätt tak på vitt
GAIN_MIN = 512


@dataclass
class WhiteResult:
    gains: dict
    reading: object
    reached: bool
    history: list = field(default_factory=list)   # (gains, Reading)


def apply_preset_gains(tv, mode: str, gains: dict) -> None:
    """Skriver förinställningen och laddar om läget; först då når värdena HAL:en."""
    for c in CHANNELS:
        key = f"Color_Temperature_{mode}_{c}_Gain"
        if tv.get(key) != str(gains[c]):
            tv.set(key, gains[c])
    tv.set("Color_Temperature", "Cool" if mode != "Cool" else "Warm")
    tv.set("Color_Temperature", mode)


def _solve2(a, b, c, d, e, f):
    """Löser [[a, b], [c, d]]·u = [e, f]."""
    det = a * d - b * c
    if abs(det) < 1e-12:
        return None
    return ((e * d - b * f) / det, (a * f - e * c) / det)


def whitepoint(tv, show, measure, target_xy=(0.3127, 0.3290), mode: str = "Warm",
               tol: float = 0.0015, max_iter: int = 6, probe: int = 24) -> WhiteResult:
    """Ställer vitt på target_xy med förinställd 2-punkts gain.

    Gain kan bara sänkas från taket på vitt, så en kanal hålls på taket och de två andra
    räknas fram. Känsligheten (dx, dy per gain-steg) uppskattas med provsteg på `probe`
    och används i en Newton-iteration; den uppskattas om ifall felet inte minskar.
    """
    show(1.0)
    history = []
    gains = {c: int(tv.get(f"Color_Temperature_{mode}_{c}_Gain")) for c in CHANNELS}

    def at(g):
        apply_preset_gains(tv, mode, g)
        r = measure()
        history.append((dict(g), r))
        return r

    def err(r):
        return (target_xy[0] - r.x, target_xy[1] - r.y)

    def jacobian(g, r):
        jac = {}
        for c in CHANNELS:
            trial = dict(g)
            step = -probe if g[c] - probe >= GAIN_MIN else probe
            trial[c] = min(GAIN_CAP[c], g[c] + step)
            rt = at(trial)
            jac[c] = ((rt.x - r.x) / (trial[c] - g[c]), (rt.y - r.y) / (trial[c] - g[c]))
        return jac

    r = at(gains)
    jac = jacobian(gains, r)
    for _ in range(max_iter):
        ex, ey = err(r)
        if max(abs(ex), abs(ey)) <= tol:
            break
        candidates = []
        for fixed in CHANNELS:
            others = [c for c in CHANNELS if c != fixed]
            move = GAIN_CAP[fixed] - gains[fixed]
            rx, ry = ex - jac[fixed][0] * move, ey - jac[fixed][1] * move
            sol = _solve2(jac[others[0]][0], jac[others[1]][0], jac[others[0]][1], jac[others[1]][1],
                          rx, ry)
            if sol is None:
                continue
            new = dict(gains)
            new[fixed] = GAIN_CAP[fixed]
            for c, d in zip(others, sol):
                new[c] = round(gains[c] + d)
            if all(GAIN_MIN <= new[c] <= GAIN_CAP[c] for c in CHANNELS):
                candidates.append(new)
        if not candidates:
            break
        new = max(candidates, key=lambda g: sum(g.values()))
        if new == gains:
            break
        r_new = at(new)
        if max(map(abs, err(r_new))) >= max(abs(ex), abs(ey)):
            jac = jacobian(new, r_new)
        gains, r = new, r_new

    best_gains, best = min(history, key=lambda h: max(map(abs, err(h[1]))))
    if history[-1][0] != best_gains:
        apply_preset_gains(tv, mode, best_gains)
    return WhiteResult(best_gains, best, max(map(abs, err(best))) <= tol, history)


GAMMA_PRESETS = ("Gamma18", "Gamma20", "Gamma22", "Gamma24", "Gamma26")
UNCORRECTED_LEVELS = (0.70, 0.80, 0.90)   # ovanför flerpunkts vitbalansens 5–60 %


@dataclass
class GammaResult:
    preset: str
    error: float                                  # medel av |effektiv gamma − mål|
    history: dict = field(default_factory=dict)   # förval -> {nivå: Y}


def gamma_preset(tv, show, measure, white_y: float, target: float = 2.2,
                 levels=UNCORRECTED_LEVELS, presets=GAMMA_PRESETS) -> GammaResult:
    """Väljer det gammaförval som ligger närmast målet där inget annat kan rätta det.

    Nivåerna 5–60 % rättas sedan av flerpunkts vitbalansen, så bara nivåerna ovanför räknas.
    Förvalen ändrar inte vitt (uppmätt), så white_y mäts en gång före.
    """
    import math
    history = {}
    for level in levels:                 # ett mönsterbyte per nivå, förvalen växlas på plats
        show(level)
        for preset in presets:
            tv.set("Gamma", preset)
            history.setdefault(preset, {})[level] = measure().Y
    def error(p):
        return sum(abs(math.log(y / white_y) / math.log(lv) - target)
                   for lv, y in history[p].items()) / len(levels)
    best = min(presets, key=error)
    tv.set("Gamma", best)
    return GammaResult(best, error(best), history)


@dataclass
class PointResult:
    index: int
    level: float
    values: dict
    reading: object
    target: object
    delta_e: float
    reached: bool
    measurements: int


def point_level(index: int) -> float:
    """Punkt i i flerpunkts vitbalansen styr grånivån 5 % × (i + 1) (uppmätt)."""
    return 0.05 * (index + 1)


def _solve3(m, v):
    def det(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    d = det(m)
    if abs(d) < 1e-15:
        return None
    out = []
    for col in range(3):
        mc = [row[:] for row in m]
        for r in range(3):
            mc[r][col] = v[r]
        out.append(det(mc) / d)
    return out


def solve_three(tv, keys: dict, measure, target, white_y: float, white_xy=(0.3127, 0.3290),
                tol_de: float = 1.0, max_iter: int = 4, probe: int = 8, lo: int = 0, hi: int = 100):
    """Ställer tre reglage (namn -> nyckel) så att mätningen hamnar på target (Reading).

    Känsligheten uppskattas med ett provsteg per reglage (probe; negativt = nedåt) och används
    i en linjär lösning i XYZ, som upprepas. Det bästa uppmätta läget behålls. Returnerar
    (värden, mätning, ΔE00, antal mätningar). Mönstret ska redan visas.
    """
    from .color import gray_delta_e, xyy_to_xyz

    names = list(keys)
    target_xyz = xyy_to_xyz(target.x, target.y, target.Y)
    values = {n: int(tv.get(keys[n])) for n in names}
    count = 0
    applied = dict(values)   # det som senast skrevs; provstegen lämnar TV:n i ett annat läge

    def at(vals):
        nonlocal count, applied
        for n in names:
            if applied[n] != vals[n]:
                tv.set(keys[n], vals[n])
        applied = dict(vals)
        count += 1
        r = measure()
        return r, xyy_to_xyz(r.x, r.y, r.Y)

    def de(r):
        return gray_delta_e(r, target, white_y, white_xy)

    r, xyz = at(values)
    tried = [(dict(values), r)]
    jac = {}
    for n in names:
        trial = dict(values)
        step = probe if lo <= values[n] + probe <= hi else -probe
        trial[n] = values[n] + step
        rt, xyz_t = at(trial)
        tried.append((dict(trial), rt))
        jac[n] = [(a - b) / (trial[n] - values[n]) for a, b in zip(xyz_t, xyz)]
    for _ in range(max_iter):
        if de(r) <= tol_de:
            break
        m = [[jac[n][row] for n in names] for row in range(3)]
        sol = _solve3(m, [t - a for t, a in zip(target_xyz, xyz)])
        if sol is None:
            break
        new = {n: max(lo, min(hi, round(values[n] + d))) for n, d in zip(names, sol)}
        if new == values:
            break
        r, xyz = at(new)
        values = new
        tried.append((dict(values), r))
    best_vals, best = min(tried, key=lambda t: de(t[1]))
    for n in names:
        if applied[n] != best_vals[n]:
            tv.set(keys[n], best_vals[n])
    return best_vals, best, de(best), count


def multipoint(tv, show, measure, white_y: float, gamma: float = 2.2,
               target_xy=(0.3127, 0.3290), indices=range(12), tol_de: float = 1.0,
               max_iter: int = 4, probe: int = 8, log=None) -> list[PointResult]:
    """Ställer varje punkt i flerpunkts vitbalansen mot målets luminans och färgpunkt.

    Punkterna verkar bara på sin egen nivå, så de ställs en i taget. Sambandet mellan
    punktvärde och XYZ är nästan linjärt (uppmätt för blått).
    """
    from .color import gray_target

    tv.set("PQ_WB_11_Point_enabled", "On")
    results = []
    for i in indices:
        level = point_level(i)
        target = gray_target(level, white_y, gamma, target_xy)
        show(level)
        vals, best, de, count = solve_three(
            tv, {c: f"PQ_WB_11_Point_{i}_{c}" for c in CHANNELS}, measure, target, white_y,
            target_xy, tol_de, max_iter, probe)
        res = PointResult(i, level, vals, best, target, de, de <= tol_de, count)
        if log:
            log(res)
        results.append(res)
    return results


# Färghanteringens färger: nyckelns bokstav och signalvärdet för 100 %.
TUNER_COLORS = {"R": (1, 0, 0), "G": (0, 1, 0), "B": (0, 0, 1),
                "C": (0, 1, 1), "M": (1, 0, 1), "Y": (1, 1, 0)}


@dataclass
class ColorResult:
    name: str
    values: dict
    reading: object
    target: object
    delta_e: float
    reached: bool
    measurements: int


def pattern_search(tv, keys: dict, measure, target, white_y: float, tol_de: float = 1.0,
                   step: int = 4, budget: int = 24, lo: int = 0, hi: int = 100,
                   min_gain: float = 0.05):
    """Mönstersökning på ΔE2000: ett reglage i taget ±step, förbättringar behålls och steget
    halveras när inget hjälper. Klarar reglage med knyck, där en linjär modell spårar ur.
    Ett steg räknas bara om ΔE00 sjunker med minst min_gain, så att mätbrus och reglage
    som inget gör inte äter upp mätningarna.

    Returnerar (värden, mätning, ΔE00, antal mätningar). Mönstret ska redan visas.
    """
    from .color import gray_delta_e

    names = list(keys)
    values = {n: int(tv.get(keys[n])) for n in names}
    applied = dict(values)
    count = 0

    def at(vals):
        """Skriver vals, mäter och returnerar (ΔE00, mätning)."""
        nonlocal count, applied
        for n in names:
            if applied[n] != vals[n]:
                tv.set(keys[n], vals[n])
        applied = dict(vals)
        count += 1
        r = measure()
        return gray_delta_e(r, target, white_y), r

    best_de, best_r = at(values)
    while step >= 1 and best_de > tol_de and count < budget:
        improved = False
        for n in names:
            for d in (step, -step):
                moved = False
                # Fortsätt åt samma håll så länge det blir bättre.
                while count < budget and best_de > tol_de:
                    trial = dict(values)
                    trial[n] = max(lo, min(hi, values[n] + d))
                    if trial == values:
                        break
                    de, r = at(trial)
                    if de > best_de - min_gain:
                        break
                    values, best_de, best_r, moved = trial, de, r, True
                if moved:
                    improved = True
                    break
        if not improved:
            step //= 2
    for n in names:
        if applied[n] != values[n]:
            tv.set(keys[n], values[n])
    return values, best_r, best_de, count


def colors(tv, show_rgb, measure, white_y: float, gamma: float = 2.2, names=tuple(TUNER_COLORS),
           tol_de: float = 1.0, budget: int = 24, log=None) -> list[ColorResult]:
    """Ställer nyans, mättnad och ljus (COLORTUNER_H/S/Y_<färg>) mot BT.709 för varje färg.

    Reglagen verkar bara på sin egen färg (uppmätt), så färgerna ställs en i taget på 100 %.
    Gråskalan påverkas inte. Målet räknas från uppmätt vitt.

    Reglagen har en knyck vid 50 (uppmätt för rött): under 50 svarar alla tre mjukt, över 50
    gör mättnaden ingenting och nyansen mest ljuset. En linjär lösning spårade ur på TV:n,
    så färgerna ställs med mönstersökning på ΔE2000.
    """
    from .color import rgb_target

    tv.set("COLORTUNER_SWITCH", "On")
    results = []
    for f in names:
        rgb = TUNER_COLORS[f]
        target = rgb_target(rgb, white_y, gamma)
        show_rgb(rgb)
        vals, best, de, count = pattern_search(
            tv, {a: f"COLORTUNER_{a}_{f}" for a in "HSY"}, measure, target, white_y,
            tol_de=tol_de, budget=budget)
        res = ColorResult(f, vals, best, target, de, de <= tol_de, count)
        if log:
            log(res)
        results.append(res)
    return results


def compromise_white(show, measure, target_xy=(0.3127, 0.3290), level: float = 0.8):
    """Målet för vitt när den övre gråskalan har en egen färgton.

    Över 60 % finns ingen punkt i flerpunkts vitbalansen, och på TV:n ligger 65–95 % högre i y
    än vitt. Vitt läggs därför halvvägs åt andra hållet, så att 100 % och `level` får lika stort
    fel. Returnerar (målets x, y) och förskjutningen som mättes.
    """
    show(1.0)
    white = measure()
    show(level)
    upper = measure()
    dx, dy = upper.x - white.x, upper.y - white.y
    return (target_xy[0] - dx / 2, target_xy[1] - dy / 2), (dx, dy)
