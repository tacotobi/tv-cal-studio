"""Kommandoraden: tvcal check | measure."""

import argparse
import datetime
import shutil
import sys
from pathlib import Path

from . import measure
from .meter import Meter, MeterError
from .patterns import ROOT, gray_video
from .tv import TV, TVError

DEFAULT_TV = "192.168.1.50"
# Nycklar som visar läget mätningen gjordes i. Läses före varje mätning och sparas i rapporten.
STATE_KEYS = ["Backlight", "Gamma", "Color_Temperature", "Color_Temperature_Warm_Red_Gain",
              "Color_Temperature_Warm_Green_Gain", "Color_Temperature_Warm_Blue_Gain",
              "PQ_WB_11_Point_enabled", "LD_MODE", "Global_Dimming"]


def cmd_check(args) -> int:
    ok = True
    for tool in ("adb", "spotread", "ffmpeg"):
        found = shutil.which(tool)
        print(f"  {'OK ' if found else 'FEL'}  {tool}")
        ok &= bool(found)
    tv = TV(args.tv)
    try:
        tv.connect()
        for key in STATE_KEYS:
            print(f"  OK   {key}={tv.get(key)}")
    except TVError as e:
        print(f"  FEL  {e}")
        ok = False
    return 0 if ok else 1


def cmd_measure(args) -> int:
    tv = TV(args.tv)
    meter = Meter(ccss=args.ccss)
    try:
        tv.connect()
        state = {key: tv.get(key) for key in STATE_KEYS}
        levels = measure.default_levels(args.step)
        rows = measure.grayscale(lambda lv: tv.show_video(gray_video(lv, args.window)),
                                 meter.measure, levels)
    except (TVError, MeterError) as e:
        print(f"FEL: {e}", file=sys.stderr)
        return 1
    finally:
        try:
            tv.home()
        except Exception:
            pass
    now = datetime.datetime.now()
    title = f"Gråskala {now:%Y-%m-%d %H:%M}, fönster {args.window} %"
    path = measure.save(rows, Path(args.out) / f"{now:%Y-%m-%d_%H%M%S}", "measure",
                        {"title": title, "tv": tv.target, "window": args.window,
                         "ccss": args.ccss, "state": state})
    print(path.read_text())
    print(f"Rapport: {path}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tvcal", description="Kalibrering av Xiaomi MiTV-MOEU0")
    p.add_argument("--tv", default=DEFAULT_TV, help="TV:ns adress (ip[:port])")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="verktyg, TV och nuvarande bildinställningar")
    m = sub.add_parser("measure", help="mät gråskalan mot D65 och gamma 2,2; skriver inget till TV:n")
    m.add_argument("--step", type=int, default=5, help="steg i procent (standard 5)")
    m.add_argument("--window", type=int, default=10, help="rutans andel av ytan i procent")
    m.add_argument("--ccss", help="spektralkorrigering för mätaren (spotread -X)")
    m.add_argument("--out", default=str(ROOT / "data" / "runs"))
    args = p.parse_args(argv)
    return {"check": cmd_check, "measure": cmd_measure}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
