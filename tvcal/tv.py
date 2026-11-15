"""TV:n via adb och provappen se.tvcal.pqprobe.

Provappen startas med `am start` för varje läsning och skrivning. Det tar 2–3 s per anrop;
byggplanen ersätter det med ett socketprotokoll i en egen app när det behövs.
"""

import subprocess
import time
from pathlib import Path

PKG = "se.tvcal.pqprobe"
FILES = f"/sdcard/Android/data/{PKG}/files"
RESULT = f"{FILES}/out.txt"


class TVError(RuntimeError):
    pass


class TV:
    def __init__(self, target: str, retries: int = 3):
        self.target = target if ":" in target else f"{target}:5555"
        self.retries = retries
        self._pushed: set[str] = set()

    def _adb(self, *args: str, check: bool = False) -> str:
        proc = subprocess.run(["adb", "-s", self.target, *args], capture_output=True, text=True,
                              timeout=60)
        if check and proc.returncode != 0:
            raise TVError(f"adb {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
        return proc.stdout.replace("\r", "")

    def shell(self, *args: str) -> str:
        return self._adb("shell", *args)

    def connect(self) -> None:
        subprocess.run(["adb", "connect", self.target], capture_output=True, timeout=30)
        if self._adb("get-state").strip() != "device":
            raise TVError(f"TV:n svarar inte på {self.target}")
        if f"package:{PKG}" not in self.shell("pm", "list", "packages", PKG).split():
            raise TVError(f"provappen {PKG} är inte installerad på TV:n")

    def _probe(self, key: str, *extra: str) -> str | None:
        """Kör provappen och returnerar nyckelns värde efteråt, None om inget svar kom.

        Resultatfilen tas bort först, så att ett anrop som aldrig nådde fram inte kan se ut
        att ha lyckats med ett gammalt svar. Ett tomt värde (offset-nycklarna) är "".
        """
        self.shell("rm", "-f", RESULT)
        self.shell("am", "start", "-W", "-n", f"{PKG}/.ProbeActivity", "--es", "paths", "none",
                   "--es", "keys", key, *extra)
        time.sleep(1)
        for line in self.shell("cat", RESULT).splitlines():
            if line.startswith(key + "="):
                return line[len(key) + 1:]
        return None

    def get(self, key: str) -> str:
        for _ in range(self.retries):
            value = self._probe(key)
            if value is not None:
                return value
            self._reconnect()
        raise TVError(f"kunde inte läsa {key}")

    def set(self, key: str, value: str | int) -> None:
        """Skriver och läser tillbaka. Anslutningen kan brytas kort, därför flera försök."""
        value = str(value)
        for _ in range(self.retries):
            if self._probe(key, "--es", "set", f"{key}={value}") == value:
                return
            self._reconnect()
        raise TVError(f"skrivningen {key}={value} gick inte igenom")

    def _reconnect(self) -> None:
        time.sleep(2)
        subprocess.run(["adb", "connect", self.target], capture_output=True, timeout=30)

    def show_video(self, path: Path, settle: float = 5.0) -> None:
        """Spelar en mönstervideo i slinga. Video hamnar i videoplanet där bildbehandlingen verkar."""
        name = path.name
        if name not in self._pushed:
            self._adb("push", str(path), f"{FILES}/{name}", check=True)
            self._pushed.add(name)
        self.shell("am", "start", "-S", "-W", "-n", f"{PKG}/.PatternActivity", "--es", "video", name)
        time.sleep(settle)

    def home(self) -> None:
        self.shell("input", "keyevent", "KEYCODE_HOME")
