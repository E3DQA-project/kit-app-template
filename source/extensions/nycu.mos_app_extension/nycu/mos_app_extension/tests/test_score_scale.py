import pathlib
import sys
import unittest


PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from score_scale import normalize_score


class ScoreScaleTests(unittest.TestCase):
    def test_normalize_score_preserves_and_snaps_half_points(self):
        self.assertEqual(normalize_score(3.5), 3.5)
        self.assertEqual(normalize_score(3.26), 3.5)
        self.assertEqual(normalize_score(3.25), 3.5)
        self.assertEqual(normalize_score("bad"), 3.0)
        self.assertEqual(normalize_score(0), 1.0)
        self.assertEqual(normalize_score(99), 5.0)


if __name__ == "__main__":
    unittest.main()
