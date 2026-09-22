import pathlib
import sys
import unittest


PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from camera_pose import normalize_camera_rotation_handedness


class CameraPoseTests(unittest.TestCase):
    def test_preserves_a_proper_right_handed_matrix3d_pose(self):
        normal = (
            (-1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, -1.0),
        )

        corrected, was_reflected = normalize_camera_rotation_handedness(normal)

        self.assertEqual(corrected, normal)
        self.assertFalse(was_reflected)

    def test_repairs_the_known_matrix3d_left_right_reflection(self):
        reflected = (
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, -1.0),
        )

        corrected, was_reflected = normalize_camera_rotation_handedness(reflected)

        self.assertEqual(
            corrected,
            (
                (-1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, -1.0),
            ),
        )
        self.assertTrue(was_reflected)

    def test_repairs_the_camera_local_x_axis_for_a_non_diagonal_pose(self):
        reflected = (
            (0.0, 0.0, 1.0),
            (0.0, 1.0, 0.0),
            (1.0, 0.0, 0.0),
        )

        corrected, was_reflected = normalize_camera_rotation_handedness(reflected)

        self.assertEqual(
            corrected,
            (
                (0.0, 0.0, 1.0),
                (0.0, 1.0, 0.0),
                (-1.0, 0.0, 0.0),
            ),
        )
        self.assertTrue(was_reflected)


if __name__ == "__main__":
    unittest.main()
