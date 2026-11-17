import unittest

from tvcal import hdr


class PQTest(unittest.TestCase):
    def test_known_points(self):
        # ST 2084: 100 cd/m² ≈ 0,5081, 1000 cd/m² ≈ 0,7518, 10 000 cd/m² = 1.
        self.assertAlmostEqual(hdr.pq_encode(100), 0.5081, places=4)
        self.assertAlmostEqual(hdr.pq_encode(1000), 0.7518, places=4)
        self.assertAlmostEqual(hdr.pq_encode(10000), 1.0, places=6)
        self.assertEqual(hdr.pq_encode(0), hdr.pq_encode(-1))

    def test_roundtrip(self):
        for nits in (0.01, 1, 10, 100, 203, 1000, 4000):
            self.assertAlmostEqual(hdr.pq_decode(hdr.pq_encode(nits)), nits, delta=nits * 1e-9)

    def test_gray_codes_match_plan(self):
        # Tabellen i HDR10-planen (10 bitar, begränsat omfång).
        table = {1: 195, 10: 327, 50: 450, 100: 509, 203: 573, 400: 636, 600: 674, 800: 701,
                 1000: 723}
        for nits, code in table.items():
            self.assertEqual(hdr.ycbcr_codes((nits, nits, nits)), (code, 512, 512))

    def test_code_to_nits_inverts_within_a_code_step(self):
        for nits in (10, 100, 1000):
            code = hdr.ycbcr_codes((nits,) * 3)[0]
            self.assertAlmostEqual(hdr.code_to_nits(code) / nits, 1, delta=0.02)

    def test_p3_primaries(self):
        for i, xy in enumerate([(0.680, 0.320), (0.265, 0.690), (0.150, 0.060)]):
            got = hdr.rgb_xy(hdr.p3_primary(i, 100))
            self.assertAlmostEqual(got[0], xy[0], delta=0.002)
            self.assertAlmostEqual(got[1], xy[1], delta=0.002)
        total = sum(hdr.rgb_luminance(hdr.p3_primary(i, 100)) for i in range(3))
        self.assertAlmostEqual(total, 100, delta=0.5)

    def test_chroma_neutral_and_clamped(self):
        self.assertEqual(hdr.limited(0.0, chroma=True), 512)
        self.assertEqual(hdr.limited(2.0), 1023)
        self.assertEqual(hdr.limited(-1.0), 0)


class ITPTest(unittest.TestCase):
    def test_d65_is_neutral(self):
        from tvcal.color import xyy_to_xyz
        i, ct, cp = hdr.ictcp(*xyy_to_xyz(0.3127, 0.3290, 100))
        self.assertAlmostEqual(i, hdr.pq_encode(100), places=3)
        self.assertAlmostEqual(ct, 0, places=3)
        self.assertAlmostEqual(cp, 0, places=3)

    def test_delta_e_itp(self):
        from tvcal.color import Reading
        ref = Reading(100, 0.3127, 0.3290)
        self.assertEqual(hdr.delta_e_itp(ref, ref), 0)
        # 1 % i luminans vid 100 cd/m² är under ett precis märkbart steg, en tydlig blåton över.
        self.assertLess(hdr.delta_e_itp(Reading(101, 0.3127, 0.3290), ref), 1)
        self.assertGreater(hdr.delta_e_itp(Reading(100, 0.2990, 0.3101), ref), 5)
        a, b = Reading(50, 0.30, 0.31), Reading(60, 0.32, 0.33)
        self.assertAlmostEqual(hdr.delta_e_itp(a, b), hdr.delta_e_itp(b, a))


if __name__ == "__main__":
    unittest.main()
