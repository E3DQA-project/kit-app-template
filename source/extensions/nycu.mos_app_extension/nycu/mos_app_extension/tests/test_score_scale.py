import pathlib
import sys
import unittest


PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from score_scale import normalize_score, score_from_slider_value, slider_value_from_score


class ScoreScaleTests(unittest.TestCase):
    def test_normalize_score_preserves_and_snaps_half_points(self):
        self.assertEqual(normalize_score(3.5), 3.5)
        self.assertEqual(normalize_score(3.26), 3.5)
        self.assertEqual(normalize_score(3.25), 3.5)
        self.assertEqual(normalize_score("bad"), 3.0)
        self.assertEqual(normalize_score(0), 1.0)
        self.assertEqual(normalize_score(99), 5.0)

    def test_integer_slider_units_round_trip_to_half_scores(self):
        self.assertEqual(score_from_slider_value(2), 1.0)
        self.assertEqual(score_from_slider_value(7), 3.5)
        self.assertEqual(score_from_slider_value(10), 5.0)
        self.assertEqual(slider_value_from_score(1.0), 2)
        self.assertEqual(slider_value_from_score(3.5), 7)
        self.assertEqual(slider_value_from_score(5.0), 10)


if __name__ == "__main__":
    unittest.main()
