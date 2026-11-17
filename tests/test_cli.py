import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tvcal import cli, snapshot
from tvcal.sim import SimMeter, SimTV


class CalibrateChainTest(unittest.TestCase):
    """Hela kedjan genom kommandoraden, mot simuleringen."""

    def run_cli(self, *argv):
        tv = SimTV()
        meter = SimMeter(tv, noise=0.002)
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.object(cli, "TV", return_value=tv), \
                mock.patch.object(cli, "Meter", return_value=meter), \
                mock.patch.object(cli, "_show", return_value=tv.show_gray), \
                mock.patch.object(cli, "_show_rgb", return_value=tv.show_rgb), \
                mock.patch("builtins.print"):
            status = cli.main(["--tv", "192.0.2.10", *argv, "--out", out])
            files = {p.name: p.read_text() for p in Path(out).rglob("*") if p.is_file()}
        return status, tv, files

    def test_all_restores_by_default(self):
        before = snapshot.take(SimTV())
        status, tv, files = self.run_cli("calibrate", "all")
        self.assertEqual(status, 0)
        self.assertEqual(snapshot.take(tv), before)
        self.assertEqual(tv.get("LD_MODE"), "High")
        self.assertEqual(tv.get("Local_Contrast"), "Middle")
        self.assertTrue({"snapshot.json", "before.txt", "after.txt", "steps.txt",
                         "colors_before.txt", "colors_after.txt"} <= set(files))

    def test_all_keep_improves_grayscale(self):
        status, tv, files = self.run_cli("calibrate", "all", "--keep")
        self.assertEqual(status, 0)
        self.assertEqual(tv.get("PQ_WB_11_Point_enabled"), "On")
        self.assertEqual(tv.get("LD_MODE"), "Off")
        self.assertEqual(tv.get("Local_Contrast"), "Off")
        from tvcal import measure
        meter = SimMeter(tv)
        rows = measure.grayscale(tv.show_gray, meter.measure, measure.default_levels(5))
        s = measure.summary(rows)
        # Målet i byggplanen: medel under 1,5 och max under 3.
        self.assertLess(s["mean_delta_e"], 1.5)
        self.assertLess(s["max_delta_e"], 3.0)
        self.assertAlmostEqual(s["white_Y"], 200.0, delta=10.0)
        # Färgerna når inte BT.709 helt (se ColorsStepTest), men ska bli bättre än före.
        def mean_de(name):
            return float(files[name].split("ΔE00 medel ")[1].split(",")[0])
        self.assertLess(mean_de("colors_after.txt"), mean_de("colors_before.txt"))


class CcssTest(unittest.TestCase):
    """Mätaren får panelens spektralkorrigering om inget annat anges."""

    def meter_ccss(self, *extra):
        tv = SimTV()
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.object(cli, "TV", return_value=tv), \
                mock.patch.object(cli, "Meter", return_value=SimMeter(tv)) as meter, \
                mock.patch.object(cli, "_show", return_value=tv.show_gray), \
                mock.patch.object(cli, "_show_rgb", return_value=tv.show_rgb), \
                mock.patch("builtins.print"):
            cli.main(["--tv", "192.0.2.10", "calibrate", "dimming", *extra, "--out", out])
        return meter.call_args.kwargs["ccss"]

    def test_default_is_panel_ccss(self):
        path = self.meter_ccss()
        self.assertEqual(path, str(cli.DEFAULT_CCSS))
        self.assertTrue(Path(path).is_file())

    def test_none_disables(self):
        self.assertIsNone(self.meter_ccss("--ccss", "none"))


class TvAddressTest(unittest.TestCase):
    """TV:ns adress står inte i koden: den ges med --tv eller TVCAL_TV."""

    def tv_address(self, argv, env):
        tv = SimTV()
        with mock.patch.dict("os.environ", env, clear=True), \
                mock.patch.object(cli, "TV", return_value=tv) as made, \
                mock.patch.object(cli, "Meter", return_value=SimMeter(tv)), \
                mock.patch("builtins.print"):
            cli.main([*argv, "check"])
        return made.call_args.args[0]

    def test_flag(self):
        self.assertEqual(self.tv_address(["--tv", "192.0.2.10"], {}), "192.0.2.10")

    def test_environment(self):
        self.assertEqual(self.tv_address([], {"TVCAL_TV": "192.0.2.11"}), "192.0.2.11")

    def test_flag_wins_over_environment(self):
        self.assertEqual(self.tv_address(["--tv", "192.0.2.10"], {"TVCAL_TV": "192.0.2.11"}),
                         "192.0.2.10")

    def test_missing_address_is_an_error(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            cli.main(["check"])


if __name__ == "__main__":
    unittest.main()
