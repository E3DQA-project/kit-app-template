import unittest

from nycu.camera_conventions import normalize_camera_rotation_handedness


class CameraHandednessTests(unittest.TestCase):
    def test_reflected_camera_local_x_is_repaired(self):
        corrected, repaired = normalize_camera_rotation_handedness(
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0))
        )

        self.assertTrue(repaired)
        self.assertEqual(corrected, ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)))

    def test_proper_rotation_is_unchanged(self):
        rotation = ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0))

        corrected, repaired = normalize_camera_rotation_handedness(rotation)

        self.assertFalse(repaired)
        self.assertEqual(corrected, rotation)

    def test_non_diagonal_reflection_repairs_only_camera_local_x(self):
        reflected = ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))

        corrected, repaired = normalize_camera_rotation_handedness(reflected)

        self.assertTrue(repaired)
        self.assertEqual(
            corrected,
            ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        )


if __name__ == "__main__":
    unittest.main()
