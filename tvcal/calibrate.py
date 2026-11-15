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


def multipoint(tv, show, measure, white_y: float, gamma: float = 2.2,
               target_xy=(0.3127, 0.3290), indices=range(12), tol_de: float = 1.0,
               max_iter: int = 4, probe: int = 8, log=None) -> list[PointResult]:
    """Ställer varje punkt i flerpunkts vitbalansen mot målets luminans och färgpunkt.

    Punkterna verkar bara på sin egen nivå, så de ställs en i taget. Sambandet mellan
    punktvärde och XYZ är nästan linjärt (uppmätt för blått), så känsligheten uppskattas
    med ett provsteg per kanal och används i en linjär lösning i XYZ, som upprepas.
    """
    from .color import Reading, gray_delta_e, gray_target, xyy_to_xyz

    tv.set("PQ_WB_11_Point_enabled", "On")
    results = []
    for i in indices:
        level = point_level(i)
        target = gray_target(level, white_y, gamma, target_xy)
        target_xyz = xyy_to_xyz(target.x, target.y, target.Y)
        keys = {c: f"PQ_WB_11_Point_{i}_{c}" for c in CHANNELS}
        values = {c: int(tv.get(keys[c])) for c in CHANNELS}
        show(level)
        count = 0

        def at(vals):
            nonlocal count
            for c in CHANNELS:
                if tv.get(keys[c]) != str(vals[c]):
                    tv.set(keys[c], vals[c])
            count += 1
            r = measure()
            return r, xyy_to_xyz(r.x, r.y, r.Y)

        tried = []
        r, xyz = at(values)
        tried.append((dict(values), r))
        jac = {}
        for c in CHANNELS:
            trial = dict(values)
            trial[c] = values[c] + (probe if values[c] + probe <= 100 else -probe)
            rt, xyz_t = at(trial)
            tried.append((dict(trial), rt))
            jac[c] = [(a - b) / (trial[c] - values[c]) for a, b in zip(xyz_t, xyz)]
        for _ in range(max_iter):
            if gray_delta_e(r, target, white_y, target_xy) <= tol_de:
                break
            m = [[jac[c][row] for c in CHANNELS] for row in range(3)]
            sol = _solve3(m, [t - a for t, a in zip(target_xyz, xyz)])
            if sol is None:
                break
            new = {c: max(0, min(100, round(values[c] + d))) for c, d in zip(CHANNELS, sol)}
            if new == values:
                break
            r, xyz = at(new)
            values = new
            tried.append((dict(values), r))
        best_vals, best = min(tried, key=lambda t: gray_delta_e(t[1], target, white_y, target_xy))
        if best_vals != values:
            for c in CHANNELS:
                tv.set(keys[c], best_vals[c])
        de = gray_delta_e(best, target, white_y, target_xy)
        res = PointResult(i, level, best_vals, best, target, de, de <= tol_de, count)
        if log:
            log(res)
        results.append(res)
    return results
