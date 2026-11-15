"""i1Display Pro via ArgyllCMS spotread."""

import re
import subprocess

from .color import Reading

_YXY = re.compile(r"Yxy:\s*([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)")


def parse_spotread(output: str) -> Reading | None:
    match = _YXY.search(output)
    return Reading(*map(float, match.groups())) if match else None


class MeterError(RuntimeError):
    pass


class Meter:
    """Mäter med två avläsningar och tar en tredje om de skiljer sig mer än tol.

    Skärmen driver omkring 1 % under ett svep, så två avläsningar i rad ska ligga nära varandra.
    """

    def __init__(self, ccss: str | None = None, tol: float = 0.01, read=None):
        self.ccss = ccss
        self.tol = tol
        self._read = read or self._spotread

    def _spotread(self) -> Reading:
        cmd = ["spotread", "-e", "-x", "-O"]
        if self.ccss:
            cmd[1:1] = ["-X", self.ccss]
        try:
            out = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                 timeout=90).stdout
        except subprocess.TimeoutExpired as e:
            raise MeterError("spotread svarade inte inom 90 s") from e
        reading = parse_spotread(out)
        if reading is None:
            raise MeterError("spotread gav ingen mätning:\n" + out[-500:])
        return reading

    def measure(self) -> Reading:
        readings = [self._read(), self._read()]
        if not self._close(*readings):
            third = self._read()
            # Av tre avläsningar används de två som ligger närmast varandra.
            pairs = [(readings[0], readings[1]), (readings[0], third), (readings[1], third)]
            readings = list(min(pairs, key=lambda p: abs(p[0].Y - p[1].Y)))
            if not self._close(*readings):
                raise MeterError(f"avläsningarna skiljer sig för mycket: {readings}")
        return Reading(*(sum(v) / 2 for v in zip(*readings)))

    def _close(self, a: Reading, b: Reading) -> bool:
        # Under cirka 0,05 cd/m² är brus i absoluta tal större än det relativa måttet.
        return abs(a.Y - b.Y) <= max(self.tol * max(a.Y, b.Y), 0.005)
