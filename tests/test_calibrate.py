import unittest

from tvcal import calibrate
from tvcal.sim import SimMeter, SimTV


def rig(noise=0.0, **kw):
    tv = SimTV(**kw)
    return tv, tv.show_gray, SimMeter(tv, noise=noise).measure


class BacklightTest(unittest.TestCase):
    def test_reaches_200(self):
        tv, show, measure = rig()
        res = calibrate.backlight(tv, show, measure, target_y=200.0)
        self.assertTrue(res.reached)
        self.assertLess(abs(res.Y - 200.0) / 200.0, 0.02)
        self.assertEqual(tv.get("Backlight"), str(res.value))

    def test_picks_closest_neighbour(self):
        # Med ojämna steg ska det närmaste av de uppmätta värdena väljas, inte det sista.
        tv, show, measure = rig()
        res = calibrate.backlight(tv, show, measure, target_y=350.0)
        best = min(res.history, key=lambda h: abs(h[1] - 350.0))
        self.assertEqual(res.value, best[0])

    def test_unreachable_low_reports_clamp(self):
        tv, show, measure = rig()
        res = calibrate.backlight(tv, show, measure, target_y=100.0)
        self.assertFalse(res.reached)
        self.assertEqual(res.value, 0)

    def test_unreachable_high(self):
        tv, show, measure = rig()
        res = calibrate.backlight(tv, show, measure, target_y=900.0)
        self.assertFalse(res.reached)
        self.assertEqual(res.value, 100)

    def test_few_measurements(self):
        tv, show, measure = rig()
        res = calibrate.backlight(tv, show, measure, target_y=500.0)
        self.assertTrue(res.reached)
        self.assertLessEqual(len(res.history), 7)

    def test_with_noise(self):
        tv, show, measure = rig(noise=0.005)
        res = calibrate.backlight(tv, show, measure, target_y=250.0)
        self.assertTrue(res.reached)
        self.assertLess(abs(res.Y - 250.0) / 250.0, 0.03)


class WhitepointTest(unittest.TestCase):
    def test_reaches_d65(self):
        tv, show, measure = rig()
        res = calibrate.whitepoint(tv, show, measure)
        self.assertTrue(res.reached, res)
        self.assertAlmostEqual(res.reading.x, 0.3127, delta=0.0015)
        self.assertAlmostEqual(res.reading.y, 0.3290, delta=0.0015)

    def test_gains_within_caps_and_one_at_cap(self):
        tv, show, measure = rig()
        res = calibrate.whitepoint(tv, show, measure)
        for c, g in res.gains.items():
            self.assertLessEqual(g, calibrate.GAIN_CAP[c])
        self.assertTrue(any(res.gains[c] == calibrate.GAIN_CAP[c] for c in calibrate.CHANNELS))

    def test_result_is_in_preset_and_on_screen(self):
        tv, show, measure = rig()
        res = calibrate.whitepoint(tv, show, measure)
        for c in calibrate.CHANNELS:
            self.assertEqual(tv.get(f"Color_Temperature_Warm_{c}_Gain"), str(res.gains[c]))
            self.assertEqual(tv.get(f"Color_Temperature_{c}_Gain"), "1024")   # aktiva nyckeln orörd
        show(1.0)
        self.assertEqual(measure(), res.reading)

    def test_other_target(self):
        tv, show, measure = rig()
        res = calibrate.whitepoint(tv, show, measure, target_xy=(0.3100, 0.3250))
        self.assertTrue(res.reached)

    def test_with_noise(self):
        tv, show, measure = rig(noise=0.003)
        res = calibrate.whitepoint(tv, show, measure, tol=0.002)
        self.assertTrue(res.reached, res.history[-1])


class GammaPresetTest(unittest.TestCase):
    def test_picks_preset_for_upper_levels(self):
        tv, show, measure = rig()
        show(1.0)
        white = measure().Y
        res = calibrate.gamma_preset(tv, show, measure, white_y=white)
        self.assertEqual(tv.get("Gamma"), res.preset)
        # I simuleringen ligger Gamma22 på 2,33 med toppen upplyft, Gamma20 på 2,11.
        self.assertIn(res.preset, ("Gamma20", "Gamma22"))
        self.assertEqual(set(res.history), set(calibrate.GAMMA_PRESETS))


class MultipointTest(unittest.TestCase):
    def setUp(self):
        self.tv, self.show, self.measure = rig()
        self.show(1.0)
        self.white = self.measure().Y

    def test_all_points_reach_target(self):
        res = calibrate.multipoint(self.tv, self.show, self.measure, white_y=self.white)
        self.assertEqual([r.index for r in res], list(range(12)))
        for r in res:
            self.assertTrue(r.reached, r)
        self.assertEqual(self.tv.get("PQ_WB_11_Point_enabled"), "On")

    def test_values_stored_and_within_range(self):
        res = calibrate.multipoint(self.tv, self.show, self.measure, white_y=self.white,
                                   indices=[3])
        for c, v in res[0].values.items():
            self.assertEqual(self.tv.get(f"PQ_WB_11_Point_3_{c}"), str(v))
            self.assertTrue(0 <= v <= 100)

    def test_does_not_touch_other_points(self):
        calibrate.multipoint(self.tv, self.show, self.measure, white_y=self.white, indices=[5])
        for i in (4, 6):
            for c in calibrate.CHANNELS:
                self.assertEqual(self.tv.get(f"PQ_WB_11_Point_{i}_{c}"), "50")

    def test_with_noise(self):
        tv, show, measure = rig(noise=0.003)
        show(1.0)
        res = calibrate.multipoint(tv, show, measure, white_y=measure().Y, indices=[1, 5, 11],
                                   tol_de=1.5)
        for r in res:
            self.assertTrue(r.reached, r)


class CompromiseWhiteTest(unittest.TestCase):
    def test_splits_upper_tint(self):
        tv, show, measure = rig()
        target, (dx, dy) = calibrate.compromise_white(show, measure)
        self.assertAlmostEqual(dy, 0.004, delta=0.001)
        self.assertAlmostEqual(target[1], 0.3290 - dy / 2, places=6)

    def test_lowers_worst_upper_error(self):
        from tvcal import measure as m
        results = {}
        for compromise in (False, True):
            tv, show, measure = rig()
            target = calibrate.compromise_white(show, measure)[0] if compromise else (0.3127, 0.3290)
            calibrate.whitepoint(tv, show, measure, target_xy=target)
            rows = m.grayscale(show, measure, [0.8, 0.9, 1.0])
            results[compromise] = max(r.delta_e for r in rows if r.level >= 0.8)
        self.assertLess(results[True], results[False])


class ColorsStepTest(unittest.TestCase):
    def setUp(self):
        self.tv, self.show, self.measure = rig()
        self.show(1.0)
        self.white = self.measure().Y

    def test_colors_improve_or_stay(self):
        # Reglagen når inte alltid BT.709 (panelens rött ligger åt orange), men inget får bli sämre.
        from tvcal import color
        before = {}
        for f, rgb in calibrate.TUNER_COLORS.items():
            self.tv.show_rgb(rgb)
            before[f] = color.gray_delta_e(self.measure(), color.rgb_target(rgb, self.white), self.white)
        res = calibrate.colors(self.tv, self.tv.show_rgb, self.measure, white_y=self.white)
        self.assertEqual([r.name for r in res], list("RGBCMY"))
        for r in res:
            self.assertLessEqual(r.delta_e, before[r.name] + 1e-9, r)
            self.assertLessEqual(r.measurements, 24)
        self.assertLess(sum(r.delta_e for r in res), sum(before.values()) - 1.0)
        self.assertEqual(self.tv.get("COLORTUNER_SWITCH"), "On")

    def test_no_op_knob_left_alone(self):
        # Mättnad över 50 gör inget på TV:n; sökningen ska inte lämna den där.
        res = calibrate.colors(self.tv, self.tv.show_rgb, self.measure, white_y=self.white)
        for r in res:
            self.assertLessEqual(r.values["S"], 50, r)

    def test_gray_untouched(self):
        self.tv.show_gray(0.5)
        before = self.measure()
        calibrate.colors(self.tv, self.tv.show_rgb, self.measure, white_y=self.white, names=["R"])
        self.tv.show_gray(0.5)
        self.assertEqual(self.measure(), before)


class SolveThreeTest(unittest.TestCase):
    def test_probe_steps_are_undone_when_already_on_target(self):
        # Gult ligger inom toleransen från start; provstegen får inte bli kvar.
        tv, show, measure = rig()
        show(1.0)
        white = measure().Y
        res = calibrate.colors(tv, tv.show_rgb, measure, white_y=white, names=["Y"], tol_de=1.0)
        for a in "HSY":
            self.assertEqual(tv.get(f"COLORTUNER_{a}_Y"), str(res[0].values[a]))
        tv.show_rgb((1, 1, 0))
        self.assertEqual(measure(), res[0].reading)

    def test_stored_values_match_screen_for_points(self):
        tv, show, measure = rig()
        show(1.0)
        white = measure().Y
        for r in calibrate.multipoint(tv, show, measure, white_y=white):
            for c in calibrate.CHANNELS:
                self.assertEqual(tv.get(f"PQ_WB_11_Point_{r.index}_{c}"), str(r.values[c]))
            show(r.level)
            self.assertEqual(measure(), r.reading)


if __name__ == "__main__":
    unittest.main()
