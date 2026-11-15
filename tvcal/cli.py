"""Kommandoraden: tvcal check | measure | calibrate | restore."""

import argparse
import datetime
import shutil
import sys
from pathlib import Path

from . import calibrate, measure, snapshot
from .meter import Meter, MeterError
from .patterns import ROOT, gray_video, rgb_video
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
        color_rows = measure.colors(lambda rgb: tv.show_video(rgb_video(rgb, args.window)),
                                    meter.measure, white_y=rows[-1].Y) if args.colors else None
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
    if color_rows:
        text = measure.format_colors(color_rows, f"Färger {now:%Y-%m-%d %H:%M}")
        (path.parent / "colors.txt").write_text(text + "\n")
        print(text)
    print(f"Rapport: {path.parent}")
    return 0


def _show(tv, window):
    return lambda level: tv.show_video(gray_video(level, window))


def cmd_calibrate(args) -> int:
    """Kör valda steg. Ögonblicksbild före; återställning efteråt om inte --keep anges."""
    tv = TV(args.tv)
    meter = Meter(ccss=args.ccss)
    now = datetime.datetime.now()
    run_dir = Path(args.out) / f"{now:%Y-%m-%d_%H%M%S}"
    try:
        tv.connect()
        snap = snapshot.take(tv)
    except TVError as e:
        print(f"FEL: {e}", file=sys.stderr)
        return 1
    snapshot.save(snap, run_dir / "snapshot.json")
    print(f"Ögonblicksbild: {run_dir / 'snapshot.json'}")
    show = _show(tv, args.window)
    status = 0
    steps = ["backlight", "whitepoint", "backlight", "gamma", "multipoint", "measure"] \
        if args.steps == ["all"] else args.steps
    log = (run_dir / "steps.txt").open("a")

    def note(text):
        print(text, flush=True)
        log.write(text + "\n")
        log.flush()

    def white_y():
        show(1.0)
        return meter.measure().Y

    try:
        if args.steps == ["all"] or args.before:
            rows = measure.grayscale(show, meter.measure, measure.default_levels(5))
            measure.save(rows, run_dir, "before", {"title": "Gråskala före", "state": snap})
            note(f"Före: ΔE00 medel {measure.summary(rows)['mean_delta_e']:.2f}, "
                 f"max {measure.summary(rows)['max_delta_e']:.2f}")
        for step in steps:
            if step == "backlight":
                res = calibrate.backlight(tv, show, meter.measure, target_y=args.target_y)
                note(f"Backlight={res.value}: vitt {res.Y:.1f} cd/m² (mål {args.target_y:.0f}),"
                     f" {'nått' if res.reached else 'INTE nått'}; prov {res.history}")
            elif step == "whitepoint":
                res = calibrate.whitepoint(tv, show, meter.measure)
                note(f"Vitpunkt: gain {res.gains}, x/y {res.reading.x:.4f}/{res.reading.y:.4f},"
                     f" Y {res.reading.Y:.1f}, {'nått' if res.reached else 'INTE nått'},"
                     f" {len(res.history)} mätningar")
            elif step == "gamma":
                res = calibrate.gamma_preset(tv, show, meter.measure, white_y=white_y())
                note(f"Gamma: {res.preset} (medelfel {res.error:.3f} över 70–90 %); {res.history}")
            elif step == "multipoint":
                calibrate.multipoint(
                    tv, show, meter.measure, white_y=white_y(),
                    log=lambda r: note(f"Punkt {r.index} ({r.level * 100:.0f} %): {r.values},"
                                       f" ΔE00 {r.delta_e:.2f}, {r.measurements} mätningar"))
            elif step == "measure":
                rows = measure.grayscale(show, meter.measure, measure.default_levels(5))
                path = measure.save(rows, run_dir, "after",
                                    {"title": "Gråskala efter", "state": snapshot.take(tv)})
                note(path.read_text())
    except (TVError, MeterError) as e:
        print(f"FEL: {e}", file=sys.stderr)
        status = 1
    except KeyboardInterrupt:
        print("Avbrutet", file=sys.stderr)
        status = 130
    finally:
        if not args.keep or status:
            try:
                written = snapshot.restore(tv, snap)
                print(f"Återställt från ögonblicksbilden ({len(written)} nycklar ändrade tillbaka)")
            except TVError as e:
                print(f"VARNING: återställningen misslyckades: {e}. Kör tvcal restore "
                      f"{run_dir / 'snapshot.json'}", file=sys.stderr)
                status = status or 1
        try:
            tv.home()
        except Exception:
            pass
        log.close()
    return status


def cmd_restore(args) -> int:
    tv = TV(args.tv)
    try:
        tv.connect()
        written = snapshot.restore(tv, snapshot.load(Path(args.snapshot)))
    except TVError as e:
        print(f"FEL: {e}", file=sys.stderr)
        return 1
    print(f"Återställt: {', '.join(written) or 'inget behövde ändras'}; färgtemperaturläget omladdat")
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
    m.add_argument("--colors", action="store_true", help="mät också färgerna 100 %% och 75 %%")
    m.add_argument("--out", default=str(ROOT / "data" / "runs"))
    c = sub.add_parser("calibrate", help="kör kalibreringssteg; SKRIVER till TV:n")
    c.add_argument("steps", nargs="+",
                   choices=["all", "backlight", "whitepoint", "gamma", "multipoint", "measure"],
                   help="steg i tur och ordning; all = hela kedjan med mätning före och efter")
    c.add_argument("--before", action="store_true", help="mät gråskalan före stegen")
    c.add_argument("--target-y", type=float, default=200.0, help="vitt i cd/m² (standard 200)")
    c.add_argument("--window", type=int, default=10)
    c.add_argument("--ccss")
    c.add_argument("--keep", action="store_true", help="behåll resultatet i stället för att återställa")
    c.add_argument("--out", default=str(ROOT / "data" / "runs"))
    r = sub.add_parser("restore", help="återställ bildinställningarna från en ögonblicksbild")
    r.add_argument("snapshot")
    args = p.parse_args(argv)
    return {"check": cmd_check, "measure": cmd_measure, "calibrate": cmd_calibrate,
            "restore": cmd_restore}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
