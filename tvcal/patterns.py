"""Mönstervideor, gjorda med scripts/make_pattern.sh så att receptet bara finns på ett ställe."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_pattern.sh"
CACHE = ROOT / "data" / "patterns"


def gray_code(level: float) -> int:
    """8-bitarsvärdet för en grånivå 0–1."""
    return round(level * 255)


def rgb_video(rgb, window: int = 10) -> Path:
    """En ruta med signalvärden rgb (0–1) på window procent av ytan.

    Görs en gång och sparas i data/patterns/.
    """
    codes = [gray_code(c) for c in rgb]
    hex_ = "".join(f"{c:02x}" for c in codes)
    name = f"gray_{codes[0]:03d}_w{window}.mp4" if len(set(codes)) == 1 else f"rgb_{hex_}_w{window}.mp4"
    path = CACHE / name
    if not path.exists():
        subprocess.run([str(SCRIPT), str(path), hex_, str(window)], check=True,
                       capture_output=True, text=True)
    return path


def gray_video(level: float, window: int = 10) -> Path:
    return rgb_video((level, level, level), window)


HDR_SCRIPT = ROOT / "scripts" / "make_pattern_hdr.sh"


def hdr_video(rgb_nits, window: int = 10, max_cll: str = "1000,400") -> Path:
    """HDR10-ruta med linjärt BT.2020-RGB i cd/m² per kanal; max_cll "none" ger ingen metadata."""
    from .hdr import ycbcr_codes
    y, cb, cr = ycbcr_codes(rgb_nits)
    meta = "" if max_cll == "1000,400" else "_cll" + max_cll.replace(",", "-")
    path = CACHE / f"hdr_{y:04d}_{cb:04d}_{cr:04d}_w{window}{meta}.mp4"
    if not path.exists():
        subprocess.run([str(HDR_SCRIPT), str(path), f"{y},{cb},{cr}", str(window), max_cll],
                       check=True, capture_output=True, text=True)
    return path
