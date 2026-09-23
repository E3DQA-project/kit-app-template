"""Shared Kit gamepad look correction for the E3DQA and MOS viewers."""

import omni.ext

from .patch import install_gamepad_look_fix, uninstall_gamepad_look_fix


class GamepadLookFixExtension(omni.ext.IExt):
    def on_startup(self, _ext_id: str) -> None:
        install_gamepad_look_fix()

    def on_shutdown(self) -> None:
        uninstall_gamepad_look_fix()
