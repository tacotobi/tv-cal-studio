import unittest

from tvcal import measure
from tvcal.color import D65, Reading
from tvcal.meter import Meter, MeterError, parse_spotread


class FakeDisplay:
    """Skärm med ren potensgamma och en fast färgpunkt."""

    def __init__(self, white_y=200.0, gamma=2.2, xy=D65):
        self.white_y, self.gamma, self.xy = white_y, gamma, xy
        self.level = None
        self.shown = []

    def show(self, level):
        self.level = level
        self.shown.append(level)

    def measure(self):
        return Reading(self.white_y * self.level ** self.gamma, *self.xy)


class GrayscaleTest(unittest.TestCase):
    def test_perfect_display_has_no_error(self):
        d = FakeDisplay()
        rows = measure.grayscale(d.show, d.measure, measure.default_levels(10))
        self.assertEqual(len(rows), 10)
        for r in rows:
            self.assertAlmostEqual(r.delta_e, 0.0, places=6)
        self.assertEqual(d.shown[0], 1.0)   # vitt först, målet räknas från det

    def test_reports_effective_gamma(self):
        d = FakeDisplay(gamma=2.35)
        rows = measure.grayscale(d.show, d.measure, [0.5, 1.0])
        self.assertAlmostEqual(rows[0].gamma, 2.35, places=6)
        self.assertIsNone(rows[-1].gamma)
        self.assertGreater(rows[0].delta_e, 1.0)

    def test_levels_are_8bit_codes(self):
        d = FakeDisplay()
        rows = measure.grayscale(d.show, d.measure, [0.05])
        self.assertAlmostEqual(rows[0].level, 13 / 255)

    def test_white_is_added(self):
        d = FakeDisplay()
        rows = measure.grayscale(d.show, d.measure, [0.3])
        self.assertEqual([r.level for r in rows][-1], 1.0)

    def test_tinted_white_counts(self):
        d = FakeDisplay(xy=(0.3025, 0.3121))   # Warm som uppmätt på TV:n
        rows = measure.grayscale(d.show, d.measure, [0.5, 1.0])
        self.assertGreater(rows[-1].delta_e, 3.0)

    def test_report_mentions_summary(self):
        d = FakeDisplay()
        text = measure.format_report(measure.grayscale(d.show, d.measure, [0.5]), "prov")
        self.assertIn("ΔE00 medel 0.00", text)


class MeterTest(unittest.TestCase):
    def test_parse(self):
        out = "Place instrument...\n Result is XYZ: 1 2 3, D50 Lab: 1 2 3\n" \
              "                           Yxy: 344.021712 0.302231 0.311533\n"
        self.assertEqual(parse_spotread(out), Reading(344.021712, 0.302231, 0.311533))
        self.assertIsNone(parse_spotread("Instrument not found"))

    def test_mean_of_two(self):
        reads = iter([Reading(100.0, 0.31, 0.32), Reading(100.4, 0.31, 0.32)])
        self.assertAlmostEqual(Meter(read=lambda: next(reads)).measure().Y, 100.2)

    def test_third_reading_when_apart(self):
        reads = iter([Reading(100.0, 0.31, 0.32), Reading(110.0, 0.31, 0.32),
                      Reading(100.2, 0.31, 0.32)])
        self.assertAlmostEqual(Meter(read=lambda: next(reads)).measure().Y, 100.1)

    def test_gives_up_when_all_apart(self):
        reads = iter([Reading(100.0, 0.31, 0.32), Reading(110.0, 0.31, 0.32),
                      Reading(120.0, 0.31, 0.32)])
        with self.assertRaises(MeterError):
            Meter(read=lambda: next(reads)).measure()

    def test_dark_uses_absolute_tolerance(self):
        reads = iter([Reading(0.010, 0.31, 0.32), Reading(0.013, 0.31, 0.32)])
        self.assertAlmostEqual(Meter(read=lambda: next(reads)).measure().Y, 0.0115)


if __name__ == "__main__":
    unittest.main()
