import importlib.util
from pathlib import Path
import unittest


_MODULE_PATH = Path(__file__).resolve().parents[1] / "nycu" / "gamepad_look_fix" / "patch.py"
_SPEC = importlib.util.spec_from_file_location("gamepad_fix", _MODULE_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
restore_unscaled_look_state = _MODULE.restore_unscaled_look_state


class _Action:
    def __init__(self, mode):
        self.mode = mode


class _Model:
    def __init__(self, speed):
        self.speed = speed

    def get_item(self, name):
        assert name == "look_speed"
        return name

    def get_as_floats(self, item):
        assert item == "look_speed"
        return self.speed


class _Manipulator:
    def __init__(self, model):
        self.model = model


class _Controller:
    def __init__(self, previous, speed, event_mode="look"):
        self._GamePadController__compressed_events = {"other_axis": 0.0}
        self._GamePadController__value_actions = {"other_axis": _Action(event_mode)}
        self._GamePadController__action_modes = {"look": previous}
        self._GamePadController__manipulator = _Manipulator(_Model(speed))


class RestoreLookStateTests(unittest.TestCase):
    def test_horizontal_value_does_not_flip_on_vertical_event(self):
        controller = _Controller([-1.0, 0.0, 0.0], [-1.0, 0.5])
        restore_unscaled_look_state(controller)
        self.assertEqual(controller._GamePadController__action_modes["look"], [1.0, 0.0, 0.0])

    def test_vertical_value_does_not_shrink_on_horizontal_event(self):
        controller = _Controller([0.0, 0.5, 0.0], [-1.0, 0.5])
        restore_unscaled_look_state(controller)
        self.assertEqual(controller._GamePadController__action_modes["look"], [-0.0, 1.0, 0.0])

    def test_other_actions_leave_look_state_alone(self):
        controller = _Controller([-1.0, 0.5, 0.0], [-1.0, 0.5], event_mode="fly")
        restore_unscaled_look_state(controller)
        self.assertEqual(controller._GamePadController__action_modes["look"], [-1.0, 0.5, 0.0])


if __name__ == "__main__":
    unittest.main()
