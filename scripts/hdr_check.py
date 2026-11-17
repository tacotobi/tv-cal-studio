#!/usr/bin/env python3
"""Fas 1 i HDR10-planen: når HDR10-mönster panelen, och hur ser kurvan ut?

Kontroll 3–6 i plans/2026-11-17-hdr10.md (Cortex): PQ-kurvan i grått, ytans och
lokaldämpningens betydelse, primärerna och metadatans inverkan. Kontroll 7–8 provar om
vitbalansens gain och flerpunkts vitbalansen verkar i HDR10-läget. Kontroll 4, 7 och 8 skriver
till TV:n, bara medan ett HDR10-mönster visas, och sätter tillbaka värdena efteråt.

Användning: scripts/hdr_check.py [--tv ip] [--ccss fil|none] [--only 3,4,5,6,7,8]
Resultat: data/runs/<tid>_hdr10/ med report.txt och results.json.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tvcal import hdr, patterns  # noqa: E402
from tvcal.color import D65  # noqa: E402
from tvcal.meter import Meter  # noqa: E402
from tvcal.tv import TV  # noqa: E402

GRAYS = [0.1, 1, 5, 10, 20, 50, 100, 150, 203, 300, 400, 500, 600, 700, 800, 1000, 1500, 2000,
         4000]
DEFAULT_CCSS = ROOT / "ccss" / "qd-miniled-tcl-50c7k.ccss"


class Run:
    def __init__(self, tv: TV, meter: Meter, out: Path):
        self.tv, self.meter, self.out = tv, meter, out
        self.results: dict = {}
        self.lines: list[str] = []

    def say(self, line: str = "") -> None:
        print(line, flush=True)
        self.lines.append(line)

    def show(self, rgb, window=10, max_cll="1000,400"):
        """Visar mönstret och kontrollerar att TV:n står i HDR10; returnerar mätningen."""
        video = patterns.hdr_video(rgb, window, max_cll)
        self.tv.show_video(video, settle=8)
        mode = self.hdr_type()
        if mode != "HDR10":
            raise SystemExit(f"TV:n står i {mode}, inte HDR10, för {video.name} – avbryter")
        return self.meter.measure()

    def hdr_type(self) -> str:
        self.tv.shell("rm", "-f", "/sdcard/Android/data/se.tvcal.pqprobe/files/out.txt")
        self.tv.shell("am", "start", "-W", "-n", "se.tvcal.pqprobe/.ProbeActivity",
                      "--es", "paths", "hdr", "--es", "keys", "none")
        time.sleep(1)
        lines = self.tv.shell("cat", "/sdcard/Android/data/se.tvcal.pqprobe/files/out.txt").split("\n")
        return lines[2].strip() if len(lines) > 2 else "?"

    def save(self) -> None:
        (self.out / "results.json").write_text(json.dumps(self.results, indent=1))
        (self.out / "report.txt").write_text("\n".join(self.lines) + "\n")

    # Kontroll 3: grått på 10 % mot PQ.
    def gray(self) -> None:
        self.say("Kontroll 3 – grått, ruta 10 %, mot PQ (ST 2084)")
        self.say(f"{'mål':>8} {'kod':>4} {'kodens':>8} {'mätt':>9} {'kvot':>6} {'x':>7} {'y':>7}")
        rows = []
        for nits in GRAYS:
            code = hdr.ycbcr_codes((nits,) * 3)[0]
            exact = hdr.code_to_nits(code)
            r = self.show((nits,) * 3)
            rows.append({"target": nits, "code": code, "code_nits": exact, "Y": r.Y, "x": r.x, "y": r.y})
            self.say(f"{nits:8.1f} {code:4d} {exact:8.2f} {r.Y:9.3f} {r.Y / exact:6.3f} "
                     f"{r.x:7.4f} {r.y:7.4f}")
            self.results["gray"] = rows
            self.save()
        self.say(f"D65 är {D65[0]:.4f} {D65[1]:.4f}. Kvoten är mätt / kodens luminans.")
        self.say()

    # Kontroll 4: ytans och lokaldämpningens betydelse.
    def area(self) -> None:
        self.say("Kontroll 4 – yta och lokaldämpning")
        self.tv.show_video(patterns.hdr_video((100,) * 3), settle=8)
        before = self.tv.get("LD_MODE")
        self.say(f"LD_MODE i HDR10-läget före: {before}")
        rows = []
        try:
            for ld in ("Off", "High"):
                # Skrivningen ska gälla HDR10-läget, så ett HDR-mönster visas när den görs.
                self.tv.show_video(patterns.hdr_video((100,) * 3), settle=8)
                self.tv.set("LD_MODE", ld)
                for window in (2, 10, 25):
                    for nits in (100, 1000):
                        r = self.show((nits,) * 3, window)
                        rows.append({"LD_MODE": ld, "window": window, "target": nits, "Y": r.Y,
                                     "x": r.x, "y": r.y})
                        self.say(f"  LD_MODE={ld:5} ruta {window:2d} %  {nits:5d} cd/m² → {r.Y:8.2f}")
                        self.results["area"] = rows
                        self.save()
        finally:
            self.tv.show_video(patterns.hdr_video((100,) * 3), settle=8)
            self.tv.set("LD_MODE", before)
            self.say(f"LD_MODE i HDR10-läget återställt till {before}")
        self.say()

    # Kontroll 5: primärerna.
    def primaries(self) -> None:
        self.say("Kontroll 5 – P3-primärer i BT.2020 (andelar av vitt 100 cd/m²), ruta 10 %")
        rows = []
        targets = {"vitt": (100.0, 100.0, 100.0)}
        targets.update({name: hdr.p3_primary(i, 100) for i, name in enumerate(("röd", "grön", "blå"))})
        for name, rgb in targets.items():
            r = self.show(rgb)
            tx, ty = hdr.rgb_xy(rgb)
            ty_ = hdr.rgb_luminance(rgb)
            rows.append({"name": name, "Y": r.Y, "x": r.x, "y": r.y, "target_Y": ty_,
                         "target_x": tx, "target_y": ty})
            self.say(f"  {name:5}  Y {r.Y:7.2f} (mål {ty_:6.2f})  xy {r.x:.4f} {r.y:.4f} "
                     f"(mål {tx:.4f} {ty:.4f})")
            self.results["primaries"] = rows
            self.save()
        self.say("  Som jämförelse: BT.709 röd 0,640/0,330, grön 0,300/0,600, blå 0,150/0,060.")
        self.say()

    # Kontroll 6: metadatans inverkan.
    def metadata(self) -> None:
        self.say("Kontroll 6 – metadata (max-cll), ruta 10 %")
        rows = []
        for cll in ("1000,400", "4000,400", "none"):
            for nits in (100, 1000):
                r = self.show((nits,) * 3, 10, cll)
                rows.append({"max_cll": cll, "target": nits, "Y": r.Y, "x": r.x, "y": r.y})
                self.say(f"  max-cll {cll:9}  {nits:5d} cd/m² → {r.Y:8.2f}")
                self.results["metadata"] = rows
                self.save()
        self.say()

    def hdr_set(self, key: str, value) -> None:
        """Skriver medan ett HDR10-mönster visas, så att värdet hamnar i HDR10-läget."""
        self.tv.show_video(patterns.hdr_video((100,) * 3), settle=8)
        if self.hdr_type() != "HDR10":
            raise SystemExit(f"TV:n står inte i HDR10 – skriver inte {key}")
        self.tv.set(key, value)

    def levels(self, nits_list) -> dict:
        return {n: self.show((n,) * 3) for n in nits_list}

    # Kontroll 7: verkar vitbalansens gain i HDR10-läget, och var?
    def gain(self) -> None:
        self.say("Kontroll 7 – förinställd gain (Warm) i HDR10-läget")
        levels = (10, 100, 400, 700)
        key = "Color_Temperature_Warm_Blue_Gain"
        self.tv.show_video(patterns.hdr_video((100,) * 3), settle=8)
        before = int(self.tv.get(key))
        rows = []
        try:
            base = self.levels(levels)
            self.hdr_set(key, before - 96)
            # Förinställningen verkställs först när läget laddas om (som i SDR).
            self.hdr_set("Color_Temperature", "Cool")
            self.hdr_set("Color_Temperature", "Warm")
            after = self.levels(levels)
            for n in levels:
                b, a = base[n], after[n]
                rows.append({"nits": n, "before": b._asdict(), "after": a._asdict()})
                self.say(f"  {n:4d} cd/m²  Y {b.Y:8.2f} → {a.Y:8.2f}  x {b.x:.4f} → {a.x:.4f}  "
                         f"y {b.y:.4f} → {a.y:.4f}")
            self.results["gain"] = rows
            self.save()
        finally:
            self.hdr_set(key, before)
            self.hdr_set("Color_Temperature", "Cool")
            self.hdr_set("Color_Temperature", "Warm")
            self.say(f"  {key} i HDR10-läget återställt till {before} (sänkt med 96 under provet)")
        self.say()

    # Kontroll 8: vilken nivå styr punkt 5 i flerpunkts vitbalansen i HDR10-läget?
    def points(self) -> None:
        self.say("Kontroll 8 – flerpunkts vitbalans, punkt 5 blått = 20, i HDR10-läget")
        levels = (2.43, 5.15, 10.04, 18.43, 32.45, 100)
        self.tv.show_video(patterns.hdr_video((100,) * 3), settle=8)
        enabled = self.tv.get("PQ_WB_11_Point_enabled")
        point = int(self.tv.get("PQ_WB_11_Point_5_Blue"))
        rows = []
        try:
            self.hdr_set("PQ_WB_11_Point_enabled", "On")
            base = self.levels(levels)
            self.hdr_set("PQ_WB_11_Point_5_Blue", 20)
            after = self.levels(levels)
            for n in levels:
                b, a = base[n], after[n]
                rows.append({"nits": n, "before": b._asdict(), "after": a._asdict()})
                self.say(f"  {n:6.2f} cd/m²  Y {b.Y:8.3f} → {a.Y:8.3f}  x {b.x:.4f} → {a.x:.4f}  "
                         f"y {b.y:.4f} → {a.y:.4f}")
            self.results["points"] = rows
            self.save()
        finally:
            self.hdr_set("PQ_WB_11_Point_5_Blue", point)
            self.hdr_set("PQ_WB_11_Point_enabled", enabled)
            self.say(f"  återställt: punkt 5 blått {point}, PQ_WB_11_Point_enabled={enabled}")
        self.say()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tv", default=os.environ.get("TVCAL_TV"))
    ap.add_argument("--ccss", default=str(DEFAULT_CCSS))
    ap.add_argument("--only", default="3,4,5,6")
    args = ap.parse_args()
    if not args.tv:
        ap.error("ange --tv eller TVCAL_TV")

    out = ROOT / "data" / "runs" / (datetime.now().strftime("%Y-%m-%d_%H%M%S") + "_hdr10")
    out.mkdir(parents=True)
    tv = TV(args.tv)
    tv.connect()
    run = Run(tv, Meter(None if args.ccss == "none" else args.ccss), out)
    run.say(f"HDR10-prov {datetime.now():%Y-%m-%d %H:%M}, CCSS {args.ccss}")
    run.say()
    checks = {"3": run.gray, "4": run.area, "5": run.primaries, "6": run.metadata,
              "7": run.gain, "8": run.points}
    try:
        for c in args.only.split(","):
            checks[c]()
    finally:
        run.save()
        tv.home()
    print(out)


if __name__ == "__main__":
    main()
