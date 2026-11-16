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
            status = cli.main([*argv, "--out", out])
            files = {p.name: p.read_text() for p in Path(out).rglob("*") if p.is_file()}
        return status, tv, files

    def test_all_restores_by_default(self):
        before = snapshot.take(SimTV())
        status, tv, files = self.run_cli("calibrate", "all")
        self.assertEqual(status, 0)
        self.assertEqual(snapshot.take(tv), before)
        self.assertTrue({"snapshot.json", "before.txt", "after.txt", "steps.txt",
                         "colors_before.txt", "colors_after.txt"} <= set(files))

    def test_all_keep_improves_grayscale(self):
        status, tv, files = self.run_cli("calibrate", "all", "--keep")
        self.assertEqual(status, 0)
        self.assertEqual(tv.get("PQ_WB_11_Point_enabled"), "On")
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


if __name__ == "__main__":
    unittest.main()
