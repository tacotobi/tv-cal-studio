import unittest

from tvcal import color


class DeltaE2000Test(unittest.TestCase):
    # Referenspar ur Sharma, Wu och Dalal (2005), "The CIEDE2000 Color-Difference Formula".
    PAIRS = [
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
        ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
        ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
        ((50.0, 2.49, -0.001), (50.0, -2.49, 0.0009), 7.1792),   # nyansvinkeln runt 0/360
        ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
    ]

    def test_reference_pairs(self):
        for lab1, lab2, expected in self.PAIRS:
            with self.subTest(lab1=lab1, lab2=lab2):
                self.assertAlmostEqual(color.delta_e2000(lab1, lab2), expected, places=4)

    def test_symmetric(self):
        for lab1, lab2, _ in self.PAIRS:
            self.assertAlmostEqual(color.delta_e2000(lab1, lab2), color.delta_e2000(lab2, lab1), places=9)

    def test_identical_is_zero(self):
        self.assertEqual(color.delta_e2000((40.0, 10.0, -5.0), (40.0, 10.0, -5.0)), 0.0)


class ConversionTest(unittest.TestCase):
    def test_xyy_to_xyz(self):
        X, Y, Z = color.xyy_to_xyz(0.3127, 0.3290, 100.0)
        self.assertAlmostEqual(X, 95.0455, places=3)
        self.assertAlmostEqual(Y, 100.0)
        self.assertAlmostEqual(Z, 108.9057, places=3)

    def test_white_is_l100(self):
        white = color.xyy_to_xyz(0.3127, 0.3290, 200.0)
        L, a, b = color.xyz_to_lab(white, white)
        self.assertAlmostEqual(L, 100.0)
        self.assertAlmostEqual(a, 0.0)
        self.assertAlmostEqual(b, 0.0)

    def test_dark_values_use_linear_segment(self):
        white = color.xyy_to_xyz(0.3127, 0.3290, 100.0)
        L, _, _ = color.xyz_to_lab(color.xyy_to_xyz(0.3127, 0.3290, 0.5), white)
        self.assertAlmostEqual(L, 903.2963 * 0.005, places=3)


class GrayTargetTest(unittest.TestCase):
    def test_gamma_22(self):
        target = color.gray_target(0.5, white_y=200.0, gamma=2.2)
        self.assertAlmostEqual(target.Y, 200.0 * 0.5 ** 2.2)
        self.assertEqual((target.x, target.y), color.D65)

    def test_white(self):
        self.assertAlmostEqual(color.gray_target(1.0, white_y=200.0).Y, 200.0)

    def test_level_out_of_range(self):
        with self.assertRaises(ValueError):
            color.gray_target(1.2, white_y=200.0)


class GrayErrorTest(unittest.TestCase):
    def test_on_target_is_zero(self):
        target = color.gray_target(0.3, white_y=200.0)
        self.assertAlmostEqual(color.gray_delta_e(target, target, white_y=200.0), 0.0)

    def test_chromaticity_error_counts(self):
        target = color.gray_target(0.5, white_y=200.0)
        off = color.Reading(target.Y, target.x + 0.005, target.y)
        self.assertGreater(color.gray_delta_e(off, target, white_y=200.0), 1.0)

    def test_luminance_error_counts(self):
        target = color.gray_target(0.5, white_y=200.0)
        brighter = color.Reading(target.Y * 1.1, target.x, target.y)
        self.assertGreater(color.gray_delta_e(brighter, target, white_y=200.0), 1.0)

    def test_effective_gamma(self):
        self.assertAlmostEqual(color.effective_gamma(200.0 * 0.4 ** 2.35, 200.0, 0.4), 2.35)


if __name__ == "__main__":
    unittest.main()
