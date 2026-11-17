import unittest

from tvcal import hdrcal
from tvcal.color import Reading
from tvcal.meter import MeterError
from tvcal.sim import SimHDRTV, SimMeter


class PointNitsTest(unittest.TestCase):
    def test_points_where_measured(self):
        # Svepet 2026-11-17: punkt 5 verkade mest kring 52 cd/m², punkt 9 kring 165.
        self.assertAlmostEqual(hdrcal.point_nits(5), 52, delta=3)
        self.assertAlmostEqual(hdrcal.point_nits(9), 165, delta=8)
        self.assertLess(hdrcal.point_nits(0), 1.5)
        self.assertLess(hdrcal.point_nits(11), hdrcal.WHITE_NITS)


class ScreenTest(unittest.TestCase):
    def screen(self, readings):
        shown = []
        it = iter(readings)
        return hdrcal.Screen(shown.append, lambda: next(it)), shown

    def test_restarts_pattern_before_each_reading(self):
        s, shown = self.screen([Reading(100, 0.3, 0.31)] * 2)
        s.show(100)
        s.measure()
        self.assertEqual(shown, [100, 100, 100])

    def test_odd_reading_is_dropped(self):
        good, odd = Reading(100, 0.2992, 0.3088), Reading(97.5, 0.3045, 0.3108)
        s, _ = self.screen([odd, good, good])
        s.show(100)
        r = s.measure()
        self.assertAlmostEqual(r.x, good.x)
        self.assertAlmostEqual(r.Y, good.Y)

    def test_three_disagreeing_readings_fail(self):
        s, _ = self.screen([Reading(100, 0.29, 0.31), Reading(100, 0.30, 0.31), Reading(100, 0.31, 0.31)])
        s.show(100)
        with self.assertRaises(MeterError):
            s.measure()


class ChainTest(unittest.TestCase):
    def test_whitepoint_and_points_bring_grayscale_to_d65(self):
        tv = SimHDRTV()
        meter = SimMeter(tv, noise=0.002)
        screen = hdrcal.Screen(tv.show_nits, meter.measure)
        before = hdrcal.summary(hdrcal.grayscale(screen))
        white = hdrcal.whitepoint(tv, screen)
        self.assertTrue(white.reached)
        hdrcal.multipoint(tv, screen)
        after = hdrcal.summary(hdrcal.grayscale(screen))
        self.assertGreater(before["mean_itp"], 4)
        self.assertLess(after["mean_itp"], before["mean_itp"] / 2)
        self.assertEqual(tv.get("PQ_WB_11_Point_enabled"), "On")


class CliTest(unittest.TestCase):
    def run_cli(self, *argv):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from tvcal import cli
        tv = SimHDRTV()
        meter = SimMeter(tv, noise=0.002)
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.object(cli, "TV", return_value=tv), \
                mock.patch.object(cli, "Meter", return_value=meter), \
                mock.patch.object(cli, "hdr_video", side_effect=lambda rgb, *a, **k: rgb[0]):
            status = cli.main(["--tv", "sim", "hdr10", *argv, "--out", out])
            run = next(Path(out).iterdir())
            files = {p.name: p.read_text() for p in run.iterdir()}
        return status, tv, files

    def test_calibrate_keep(self):
        status, tv, files = self.run_cli("calibrate", "--keep")
        self.assertEqual(status, 0)
        self.assertIn("before.txt", files)
        self.assertIn("after.txt", files)
        self.assertIn('"_HdrType": "HDR10"', files["snapshot.json"])
        self.assertEqual(tv.get("PQ_WB_11_Point_enabled"), "On")
        self.assertNotEqual(tv.get("Color_Temperature_Warm_Blue_Gain"), "976")

    def test_calibrate_restores_without_keep(self):
        status, tv, _ = self.run_cli("calibrate")
        self.assertEqual(status, 0)
        self.assertEqual(tv.get("PQ_WB_11_Point_enabled"), "Off")
        self.assertEqual(tv.get("Color_Temperature_Warm_Blue_Gain"), "976")
        self.assertEqual(tv.require_hdr, "HDR10")

    def test_measure_writes_nothing(self):
        status, tv, files = self.run_cli("measure")
        self.assertEqual(status, 0)
        self.assertEqual(tv.writes, 0)
        self.assertIn("measure.txt", files)


if __name__ == "__main__":
    unittest.main()
