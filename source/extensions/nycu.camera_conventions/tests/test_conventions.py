import unittest

from nycu.camera_conventions import get_camera_convention


class CameraConventionTests(unittest.TestCase):
    def test_matrix3d_uses_native_z_up_camera_coordinates(self):
        convention = get_camera_convention("Matrix-3D")

        self.assertEqual(convention.scene_orientation, "none")
        self.assertTrue(convention.force_z_up)
        self.assertFalse(convention.rotation_is_world_to_camera)
        self.assertFalse(convention.opencv_axes)
        self.assertFalse(convention.swap_yz)
        self.assertEqual(convention.camera_roll_degrees, 180)
        self.assertEqual(convention.stage_up_axis, "y")

    def test_unknown_method_is_rejected(self):
        with self.assertRaises(ValueError):
            get_camera_convention("unknown")


if __name__ == "__main__":
    unittest.main()
