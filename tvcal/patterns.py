"""Mönstervideor, gjorda med scripts/make_pattern.sh så att receptet bara finns på ett ställe."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_pattern.sh"
CACHE = ROOT / "data" / "patterns"


def gray_code(level: float) -> int:
    """8-bitarsvärdet för en grånivå 0–1."""
    return round(level * 255)


def gray_video(level: float, window: int = 10) -> Path:
    """En grå ruta på window procent av ytan. Görs en gång och sparas i data/patterns/."""
    code = gray_code(level)
    path = CACHE / f"gray_{code:03d}_w{window}.mp4"
    if not path.exists():
        hex_ = f"{code:02x}" * 3
        subprocess.run([str(SCRIPT), str(path), hex_, str(window)], check=True,
                       capture_output=True, text=True)
    return path
