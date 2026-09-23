"""Work around Kit 110.1.0 re-scaling retained gamepad look components."""


_APPLY_EVENTS = "_GamePadController__apply_events"


def restore_unscaled_look_state(controller) -> None:
    """Undo the prior scale before Kit reuses an unchanged look component."""
    events = controller._GamePadController__compressed_events
    actions = controller._GamePadController__value_actions
    if not any(actions.get(key) and actions[key].mode == "look" for key in events):
        return

    previous = controller._GamePadController__action_modes.get("look")
    if not previous:
        return

    model = controller._GamePadController__manipulator.model
    speed = model.get_as_floats(model.get_item("look_speed")) or ()
    for axis, factor in enumerate(speed[: len(previous)]):
        if factor:
            previous[axis] /= factor


def install_gamepad_look_fix() -> None:
    """Patch only Kit's gamepad event application, preserving stick directions."""
    import carb
    from omni.kit.manipulator.camera.gamepad import GamePadController

    original = getattr(GamePadController, _APPLY_EVENTS)
    if hasattr(original, "_nycu_original"):
        return

    async def apply_events_with_unscaled_state(self):
        try:
            restore_unscaled_look_state(self)
        except (AttributeError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            if not getattr(self, "_nycu_fix_warning_logged", False):
                carb.log_warn(f"NYCU gamepad look fix could not inspect Kit state: {exc}")
                self._nycu_fix_warning_logged = True
        await original(self)

    apply_events_with_unscaled_state._nycu_original = original
    setattr(GamePadController, _APPLY_EVENTS, apply_events_with_unscaled_state)
    carb.log_info("NYCU gamepad look fix installed")


def uninstall_gamepad_look_fix() -> None:
    from omni.kit.manipulator.camera.gamepad import GamePadController

    current = getattr(GamePadController, _APPLY_EVENTS)
    original = getattr(current, "_nycu_original", None)
    if original is not None:
        setattr(GamePadController, _APPLY_EVENTS, original)
