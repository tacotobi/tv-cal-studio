"""Kommandoraden: tvcal check | measure | calibrate | hdr10 | restore."""

import argparse
import datetime
import os
import shutil
import sys
from pathlib import Path

from . import calibrate, hdrcal, measure, snapshot
from .meter import Meter, MeterError
from .patterns import ROOT, gray_video, hdr_video, rgb_video
from .tv import TV, TVError

# Spektralkorrigering för QD-Mini LED, uppmätt med JETI spectraval på en TCL 50C7K (DisplayCAL:s
# databas). Ingen fil är uppmätt på just den här panelen; tolv QD-filer gav vitt inom ±0,0015 i y,
# och den här låg i mitten. Se docs/HARDWARE.md.
DEFAULT_CCSS = ROOT / "ccss" / "qd-miniled-tcl-50c7k.ccss"


def _ccss(value: str) -> str | None:
    return None if value == "none" else value
# Nycklar som visar läget mätningen gjordes i. Läses före varje mätning och sparas i rapporten.
STATE_KEYS = ["Backlight", "Gamma", "Color_Temperature", "Color_Temperature_Warm_Red_Gain",
              "Color_Temperature_Warm_Green_Gain", "Color_Temperature_Warm_Blue_Gain",
              "PQ_WB_11_Point_enabled", "LD_MODE", "Local_Contrast", "Global_Dimming"]


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


def _show_rgb(tv, window):
    return lambda rgb: tv.show_video(rgb_video(rgb, window))


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
    steps = ["dimming", "backlight", "whitepoint", "backlight", "gamma", "multipoint", "colors",
             "measure"] \
        if args.steps == ["all"] else args.steps
    show_rgb = _show_rgb(tv, args.window)
    log = (run_dir / "steps.txt").open("a")

    def note(text):
        print(text, flush=True)
        log.write(text + "\n")
        log.flush()

    note(f"Spektralkorrigering: {args.ccss or 'ingen'}")

    def white_y():
        show(1.0)
        return meter.measure().Y

    try:
        if args.steps == ["all"] or args.before:
            rows = measure.grayscale(show, meter.measure, measure.default_levels(5))
            measure.save(rows, run_dir, "before", {"title": "Gråskala före", "state": snap})
            note(f"Före: ΔE00 medel {measure.summary(rows)['mean_delta_e']:.2f}, "
                 f"max {measure.summary(rows)['max_delta_e']:.2f}")
            crows = measure.colors(show_rgb, meter.measure, white_y=rows[-1].Y)
            (run_dir / "colors_before.txt").write_text(measure.format_colors(crows, "Färger före") + "\n")
            note(f"Färger före: ΔE00 max {max(r.delta_e for r in crows):.2f}")
        for step in steps:
            if step == "dimming":
                # Lokaldämpningen släcker 5 % och trycker ner 10–20 %, och den lokala kontrasten
                # flyttar mellantonerna 2–3 %; båda efter bildinnehållet, så kurvan går bara att
                # ställa med dem avstängda. Först, eftersom dämpningen ändrar vitt.
                tv.set("LD_MODE", "Off")
                tv.set("Local_Contrast", "Off")
                note("Lokaldämpning och lokal kontrast avstängda (LD_MODE=Off, Local_Contrast=Off)")
            elif step == "backlight":
                res = calibrate.backlight(tv, show, meter.measure, target_y=args.target_y)
                note(f"Backlight={res.value}: vitt {res.Y:.1f} cd/m² (mål {args.target_y:.0f}),"
                     f" {'nått' if res.reached else 'INTE nått'}; prov {res.history}")
            elif step == "whitepoint":
                target = (0.3127, 0.3290)
                if args.white_compromise:
                    target, (dx, dy) = calibrate.compromise_white(show, meter.measure)
                    note(f"80 % ligger {dx:+.4f}/{dy:+.4f} från vitt; mål för vitt {target[0]:.4f}/{target[1]:.4f}")
                res = calibrate.whitepoint(tv, show, meter.measure, target_xy=target)
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
            elif step == "colors":
                calibrate.colors(
                    tv, show_rgb, meter.measure, white_y=white_y(),
                    log=lambda r: note(f"Färg {r.name}: {r.values}, ΔE00 medel 100/75 % {r.delta_e:.2f},"
                                       f" {r.measurements} prov"))
            elif step == "measure":
                rows = measure.grayscale(show, meter.measure, measure.default_levels(5))
                path = measure.save(rows, run_dir, "after",
                                    {"title": "Gråskala efter", "state": snapshot.take(tv)})
                note(path.read_text())
                crows = measure.colors(show_rgb, meter.measure, white_y=rows[-1].Y)
                text = measure.format_colors(crows, "Färger efter")
                (run_dir / "colors_after.txt").write_text(text + "\n")
                note(text)
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


HDR_MARK = "_HdrType"   # i ögonblicksbilden: värdena gäller den HDR-typen


def _hdr_screen(tv, meter, window):
    return hdrcal.Screen(lambda nits: tv.show_video(hdr_video((nits,) * 3, window), settle=6),
                         meter.measure)


def cmd_hdr10(args) -> int:
    """HDR10-läget: mätning, eller kalibrering med ögonblicksbild och återställning.

    TV:n lagrar bildvärdena per HDR-typ. All läsning och skrivning kräver att TV:n står i HDR10
    (provappen vägrar annars), så SDR-värdena rörs aldrig.
    """
    tv = TV(args.tv, require_hdr="HDR10")
    meter = Meter(ccss=args.ccss)
    screen = _hdr_screen(tv, meter, args.window)
    now = datetime.datetime.now()
    run_dir = Path(args.out) / f"{now:%Y-%m-%d_%H%M%S}_hdr10"
    calibrating = args.action == "calibrate"
    steps = ["dimming", "whitepoint", "multipoint"] if args.steps == ["all"] else args.steps
    snap = None
    status = 0
    run_dir.mkdir(parents=True, exist_ok=True)
    log = (run_dir / "steps.txt").open("a")

    def note(text):
        print(text, flush=True)
        log.write(text + "\n")
        log.flush()

    try:
        tv.connect()
        screen.show(100)
        state = {key: tv.get(key) for key in STATE_KEYS}
        note(f"HDR10, spektralkorrigering: {args.ccss or 'ingen'}; läge {state}")
        if calibrating:
            snap = {**snapshot.take(tv, hdrcal.KEYS), HDR_MARK: "HDR10"}
            snapshot.save(snap, run_dir / "snapshot.json")
            note(f"Ögonblicksbild: {run_dir / 'snapshot.json'}")
        if not calibrating or args.before or args.steps == ["all"]:
            rows = hdrcal.grayscale(screen)
            path = hdrcal.save(rows, run_dir, "before" if calibrating else "measure",
                               {"title": f"HDR10 gråskala {'före' if calibrating else ''} "
                                         f"{now:%Y-%m-%d %H:%M}", "state": state})
            note(path.read_text())
        for step in steps if calibrating else []:
            if step == "dimming":
                tv.set("LD_MODE", "Off")
                tv.set("Local_Contrast", "Off")
                note("Lokaldämpning och lokal kontrast avstängda i HDR10-läget")
            elif step == "whitepoint":
                res = hdrcal.whitepoint(tv, screen)
                note(f"Vitpunkt vid {hdrcal.WHITE_NITS:.0f} cd/m²: gain {res.gains}, x/y "
                     f"{res.reading.x:.4f}/{res.reading.y:.4f}, Y {res.reading.Y:.1f}, "
                     f"{'nått' if res.reached else 'INTE nått'}, {len(res.history)} mätningar")
            elif step == "multipoint":
                hdrcal.multipoint(tv, screen, log=lambda r: note(
                    f"Punkt {r.index} ({r.nits:.1f} cd/m²): {r.values}, ΔE ITP {r.delta_itp:.2f},"
                    f" {r.measurements} mätningar"))
        if calibrating:
            rows = hdrcal.grayscale(screen)
            path = hdrcal.save(rows, run_dir, "after", {"title": "HDR10 gråskala efter",
                                                        "state": snapshot.take(tv, hdrcal.KEYS)})
            note(path.read_text())
    except (TVError, MeterError) as e:
        print(f"FEL: {e}", file=sys.stderr)
        status = 1
    except KeyboardInterrupt:
        print("Avbrutet", file=sys.stderr)
        status = 130
    finally:
        if snap and (not args.keep or status):
            try:
                written = _restore_hdr(tv, snap)
                note(f"Återställt från ögonblicksbilden ({len(written)} nycklar ändrade tillbaka)")
            except TVError as e:
                print(f"VARNING: återställningen misslyckades: {e}. Kör tvcal restore "
                      f"{run_dir / 'snapshot.json'}", file=sys.stderr)
                status = status or 1
        try:
            tv.home()
        except Exception:
            pass
        log.close()
    print(f"Rapport: {run_dir}")
    return status


def _restore_hdr(tv, snap) -> list[str]:
    """Återställer en HDR-ögonblicksbild: visar ett mönster i rätt läge och kräver det läget."""
    tv.require_hdr = snap[HDR_MARK]
    tv.show_video(hdr_video((100, 100, 100)), settle=8)
    return snapshot.restore(tv, {k: v for k, v in snap.items() if k != HDR_MARK})


def cmd_restore(args) -> int:
    tv = TV(args.tv)
    try:
        tv.connect()
        snap = snapshot.load(Path(args.snapshot))
        if HDR_MARK in snap:
            written = _restore_hdr(tv, snap)
            tv.home()
        else:
            written = snapshot.restore(tv, snap)
    except TVError as e:
        print(f"FEL: {e}", file=sys.stderr)
        return 1
    print(f"Återställt: {', '.join(written) or 'inget behövde ändras'}; färgtemperaturläget omladdat")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tvcal", description="Kalibrering av Xiaomi MiTV-MOEU0")
    # Adressen står inte i koden; miljövariabeln slipper upprepas vid varje körning.
    p.add_argument("--tv", default=os.environ.get("TVCAL_TV"),
                   help="TV:ns adress (ip[:port]); standard är miljövariabeln TVCAL_TV")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="verktyg, TV och nuvarande bildinställningar")
    m = sub.add_parser("measure", help="mät gråskalan mot D65 och gamma 2,2; skriver inget till TV:n")
    m.add_argument("--step", type=int, default=5, help="steg i procent (standard 5)")
    m.add_argument("--window", type=int, default=10, help="rutans andel av ytan i procent")
    m.add_argument("--ccss", type=_ccss, default=str(DEFAULT_CCSS),
                   help="spektralkorrigering för mätaren (spotread -X); none = ingen")
    m.add_argument("--colors", action="store_true", help="mät också färgerna 100 %% och 75 %%")
    m.add_argument("--out", default=str(ROOT / "data" / "runs"))
    c = sub.add_parser("calibrate", help="kör kalibreringssteg; SKRIVER till TV:n")
    c.add_argument("steps", nargs="+",
                   choices=["all", "dimming", "backlight", "whitepoint", "gamma", "multipoint",
                            "colors", "measure"],
                   help="steg i tur och ordning; all = hela kedjan med mätning före och efter")
    c.add_argument("--before", action="store_true", help="mät gråskalan före stegen")
    c.add_argument("--no-white-compromise", dest="white_compromise", action="store_false",
                   help="ställ vitt exakt på D65 i stället för halvvägs mot den övre gråskalans ton")
    c.add_argument("--target-y", type=float, default=200.0, help="vitt i cd/m² (standard 200)")
    c.add_argument("--window", type=int, default=10)
    c.add_argument("--ccss", type=_ccss, default=str(DEFAULT_CCSS),
                   help="spektralkorrigering för mätaren; none = ingen")
    c.add_argument("--keep", action="store_true", help="behåll resultatet i stället för att återställa")
    c.add_argument("--out", default=str(ROOT / "data" / "runs"))
    h = sub.add_parser("hdr10", help="HDR10-läget: measure (skriver inget) eller calibrate (SKRIVER)")
    h.add_argument("action", choices=["measure", "calibrate"])
    h.add_argument("steps", nargs="*", default=["all"],
                   choices=["all", "dimming", "whitepoint", "multipoint"],
                   help="steg för calibrate; all = alla med mätning före och efter")
    h.add_argument("--before", action="store_true", help="mät före stegen")
    h.add_argument("--window", type=int, default=10)
    h.add_argument("--ccss", type=_ccss, default=str(DEFAULT_CCSS),
                   help="spektralkorrigering för mätaren; none = ingen")
    h.add_argument("--keep", action="store_true", help="behåll resultatet i stället för att återställa")
    h.add_argument("--out", default=str(ROOT / "data" / "runs"))
    r = sub.add_parser("restore", help="återställ bildinställningarna från en ögonblicksbild")
    r.add_argument("snapshot")
    args = p.parse_args(argv)
    if not args.tv:
        p.error("TV:ns adress saknas: ange --tv <ip> eller sätt TVCAL_TV")
    return {"check": cmd_check, "measure": cmd_measure, "calibrate": cmd_calibrate,
            "hdr10": cmd_hdr10, "restore": cmd_restore}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
