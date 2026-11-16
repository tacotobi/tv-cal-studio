"""Ögonblicksbild av bildinställningarna före en körning, och återställning från den."""

import json
from pathlib import Path

# Allt kalibreringen kan skriva. Ordningen spelar roll vid återställning: förinställd gain först,
# sedan färgtemperaturläget, som laddar om förinställningen till HAL:en.
CHANNELS = ("Red", "Green", "Blue")
KEYS = (
    ["LD_MODE", "Local_Contrast", "Backlight", "Gamma"]
    + [f"Color_Temperature_Warm_{c}_Gain" for c in CHANNELS]
    + [f"PQ_WB_11_Point_{i}_{c}" for i in range(12) for c in CHANNELS]
    + ["PQ_WB_11_Point_enabled"]
    + [f"COLORTUNER_{a}_{f}" for a in "HSY" for f in "RGBCMYF"]
    + [f"COLORTUNER_{c}_{k}" for c in "RGB" for k in ("GAIN", "OFFSET")]
    + ["COLORTUNER_SWITCH", "Color_space", "Gamut_Mapping", "Color_Temperature"]
)


MISSING = "<saknas>"   # provappens svar när nyckeln inte finns i databasen


def take(tv, keys=KEYS) -> dict[str, str]:
    """Läser alla nycklar. Nycklar som saknas på TV:n tas inte med, så de skrivs aldrig."""
    return {key: v for key in keys if (v := tv.get(key)) != MISSING}


def save(snap: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2, ensure_ascii=False))


def load(path: Path) -> dict[str, str]:
    return json.loads(path.read_text())


def restore(tv, snap: dict[str, str], only_changed: bool = True) -> list[str]:
    """Skriver tillbaka ögonblicksbilden och laddar om färgtemperaturläget.

    Returnerar nycklarna som skrevs. Läget laddas alltid om, eftersom en aktiv gain kan ha
    ersatt förinställningen i HAL:en utan att det syns i databasen.
    """
    written = []
    for key in [k for k in KEYS if k in snap and k != "Color_Temperature"]:
        if only_changed and tv.get(key) == snap[key]:
            continue
        tv.set(key, snap[key])
        written.append(key)
    mode = snap.get("Color_Temperature", tv.get("Color_Temperature"))
    tv.set("Color_Temperature", "Cool" if mode != "Cool" else "Warm")
    tv.set("Color_Temperature", mode)
    return written
