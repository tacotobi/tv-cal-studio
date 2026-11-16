import unittest

from tvcal import snapshot
from tvcal.sim import SimMeter, SimTV


class SimTVTest(unittest.TestCase):
    """Simuleringen ska ha de egenskaper som mätts på TV:n, annars testar den fel saker."""

    def white(self, tv):
        tv.show_gray(1.0)
        return SimMeter(tv).measure()

    def test_warm_white_matches_measurement(self):
        r = self.white(SimTV())
        self.assertAlmostEqual(r.Y, 357.6, delta=15)
        self.assertAlmostEqual(r.x, 0.3025, delta=0.004)
        self.assertAlmostEqual(r.y, 0.3121, delta=0.006)

    def test_backlight_28_and_29_equal(self):
        a, b = SimTV(backlight=28), SimTV(backlight=29)
        self.assertAlmostEqual(self.white(a).Y, self.white(b).Y, delta=2)

    def test_preset_gain_needs_reload(self):
        tv = SimTV()
        before = self.white(tv)
        tv.set("Color_Temperature_Warm_Blue_Gain", 926)
        self.assertEqual(self.white(tv), before)
        tv.set("Color_Temperature", "Cool")
        tv.set("Color_Temperature", "Warm")
        self.assertGreater(self.white(tv).x, before.x)

    def test_gain_above_cap_does_nothing(self):
        tv = SimTV()
        tv.set("Color_Temperature_Blue_Gain", 1024)
        a = self.white(tv)
        tv.set("Color_Temperature_Blue_Gain", 1100)
        self.assertEqual(self.white(tv), a)

    def test_point_only_affects_its_level(self):
        tv = SimTV()
        tv.set("PQ_WB_11_Point_enabled", "On")
        meter = SimMeter(tv)
        before = {}
        for lv in (0.25, 0.30, 0.35):
            tv.show_gray(lv)
            before[lv] = meter.measure()
        tv.set("PQ_WB_11_Point_5_Blue", 20)
        for lv in (0.25, 0.35):
            tv.show_gray(lv)
            self.assertEqual(meter.measure(), before[lv])
        tv.show_gray(0.30)
        self.assertGreater(meter.measure().x, before[0.30].x)

    def test_points_ignored_when_disabled(self):
        tv = SimTV()
        tv.show_gray(0.3)
        a = SimMeter(tv).measure()
        tv.set("PQ_WB_11_Point_5_Blue", 0)
        self.assertEqual(SimMeter(tv).measure(), a)

    def test_local_dimming_blacks_out_darkest_level(self):
        # Uppmätt 2026-11-16 vid Backlight=8: 5 % blev 0 i alla lägen utom Off.
        tv = SimTV(backlight=0)
        tv.show_gray(0.05)
        self.assertEqual(SimMeter(tv).measure().Y, 0.0)
        tv.set("LD_MODE", "Off")
        self.assertGreater(SimMeter(tv).measure().Y, 0.05)

    def test_tuner_knee_matches_red_sweep(self):
        tv = SimTV()
        tv.set("COLORTUNER_SWITCH", "On")
        tv.show_rgb((1, 0, 0))
        meter = SimMeter(tv)
        base = meter.measure()
        tv.set("COLORTUNER_S_R", 56)
        self.assertEqual(meter.measure(), base)               # mättnad över 50 gör inget
        tv.set("COLORTUNER_S_R", 44)
        self.assertAlmostEqual(meter.measure().Y / base.Y, 0.79, delta=0.03)
        tv.set("COLORTUNER_S_R", 50)
        tv.set("COLORTUNER_H_R", 44)
        r = meter.measure()
        self.assertAlmostEqual(r.x - base.x, -0.0085, delta=0.003)
        self.assertAlmostEqual(r.y - base.y, -0.0056, delta=0.003)


class SnapshotTest(unittest.TestCase):
    def test_restore_brings_back_preset_and_hal(self):
        tv = SimTV()
        tv.show_gray(1.0)
        before = SimMeter(tv).measure()
        snap = snapshot.take(tv)
        tv.set("Backlight", 10)
        tv.set("Color_Temperature_Warm_Red_Gain", 900)
        tv.set("Color_Temperature_Blue_Gain", 900)      # aktiv nyckel, syns inte i förinställningen
        tv.set("PQ_WB_11_Point_enabled", "On")
        written = snapshot.restore(tv, snap)
        self.assertIn("Backlight", written)
        self.assertNotIn("Gamma", written)
        self.assertEqual(SimMeter(tv).measure(), before)
        self.assertEqual(snapshot.take(tv), snap)

    def test_missing_keys_are_skipped(self):
        tv = SimTV()
        del tv.db["Gamut_Mapping"]
        snap = snapshot.take(tv)
        self.assertNotIn("Gamut_Mapping", snap)
        snapshot.restore(tv, snap)
        self.assertNotIn("Gamut_Mapping", tv.db)


if __name__ == "__main__":
    unittest.main()
