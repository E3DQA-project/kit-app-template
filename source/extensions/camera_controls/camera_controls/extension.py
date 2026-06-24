from __future__ import annotations

import carb.settings
import omni.ext
import omni.ui as ui


CAM_MOVE_VELOCITY = "/persistent/app/viewport/camMoveVelocity"
CAM_VELOCITY_MIN = "/persistent/app/viewport/camVelocityMin"
CAM_VELOCITY_MAX = "/persistent/app/viewport/camVelocityMax"
CAM_CONTEXT_MENU = "/exts/omni.kit.window.viewport/showContextMenu"
CURRENT_TOOL = "/app/viewport/currentTool"
ACTIVE_OPERATION = "/exts/omni.kit.viewport.navigation.core/activeOperation"
DEFAULT_NAV_OPERATION = "/exts/omni.kit.viewport.navigation.camera_manipulator/defaultOperation"

MOVE_ACCEL = "/persistent/app/viewport/manipulator/camera/moveAcceleration"
MOVE_DAMP = "/persistent/app/viewport/manipulator/camera/moveDampening"
FLY_ACCEL = "/persistent/app/viewport/manipulator/camera/flyAcceleration"
FLY_DAMP = "/persistent/app/viewport/manipulator/camera/flyDampening"


def _safe_get_float(settings: carb.settings.ISettings, path: str, fallback: float) -> float:
    try:
        value = settings.get_as_float(path)
        if value is None:
            return fallback
        return float(value)
    except Exception:
        return fallback


class CameraControlsExtension(omni.ext.IExt):
    def on_startup(self, _ext_id: str) -> None:
        self._settings = carb.settings.get_settings()
        self._window = ui.Window("Camera Controls", width=420, height=220)
        self._status = None

        self._apply_defaults()
        self._build_ui()

    def on_shutdown(self) -> None:
        self._status = None
        self._window = None
        self._settings = None

    def _apply_defaults(self) -> None:
        # Speed defaults requested by user.
        self._settings.set(CAM_VELOCITY_MIN, 0.01)
        current = _safe_get_float(self._settings, CAM_MOVE_VELOCITY, 0.01)
        self._settings.set(CAM_MOVE_VELOCITY, max(0.01, current))

        # Keep max valid even if user has unusual persistent config.
        vmax = _safe_get_float(self._settings, CAM_VELOCITY_MAX, 50.0)
        self._settings.set(CAM_VELOCITY_MAX, max(vmax, 0.02))

        # Prefer navigation tool + fly operation for WASD-style movement.
        self._settings.set(CURRENT_TOOL, "navigation")
        self._settings.set(ACTIVE_OPERATION, "fly")
        self._settings.set(DEFAULT_NAV_OPERATION, "fly")

        # Allow RMB drag controls by disabling RMB context menu in viewport.
        self._settings.set(CAM_CONTEXT_MENU, False)

    def _build_ui(self) -> None:
        with self._window.frame:
            with ui.VStack(spacing=8, height=0):
                ui.Label("Navigation preset: WASD + fly mode, RMB context menu disabled.", word_wrap=True)
                ui.Label("Default minimum speed is set to 0.01.", word_wrap=True)

                with ui.HStack(spacing=10, height=0):
                    ui.Label("Move Speed", width=140)
                    self._speed_model = ui.SimpleFloatModel(
                        _safe_get_float(self._settings, CAM_MOVE_VELOCITY, 0.01)
                    )
                    ui.FloatSlider(self._speed_model, min=0.01, max=5.0, width=220)

                with ui.HStack(spacing=10, height=0):
                    ui.Label("Speed Min", width=140)
                    self._speed_min_model = ui.SimpleFloatModel(
                        _safe_get_float(self._settings, CAM_VELOCITY_MIN, 0.01)
                    )
                    ui.FloatSlider(self._speed_min_model, min=0.001, max=1.0, width=220)

                with ui.HStack(spacing=10, height=0):
                    ui.Label("Speed Max", width=140)
                    self._speed_max_model = ui.SimpleFloatModel(
                        _safe_get_float(self._settings, CAM_VELOCITY_MAX, 50.0)
                    )
                    ui.FloatSlider(self._speed_max_model, min=0.1, max=200.0, width=220)

                with ui.HStack(spacing=10, height=0):
                    ui.Label("Move Accel", width=140)
                    self._move_accel_model = ui.SimpleFloatModel(
                        _safe_get_float(self._settings, MOVE_ACCEL, 1000.0)
                    )
                    ui.FloatSlider(self._move_accel_model, min=1.0, max=4000.0, width=220)

                with ui.HStack(spacing=10, height=0):
                    ui.Label("Look/Fly Damp", width=140)
                    self._fly_damp_model = ui.SimpleFloatModel(
                        _safe_get_float(self._settings, FLY_DAMP, 10.0)
                    )
                    ui.FloatSlider(self._fly_damp_model, min=0.1, max=100.0, width=220)

                with ui.HStack(spacing=10, height=0):
                    ui.Button("Apply", width=120, clicked_fn=self._on_apply_clicked)
                    ui.Button("Reapply Preset", width=140, clicked_fn=self._on_reapply_preset_clicked)
                    self._status = ui.Label("", word_wrap=True)

    def _set_status(self, msg: str) -> None:
        if self._status is not None:
            self._status.text = msg

    def _on_reapply_preset_clicked(self) -> None:
        self._apply_defaults()
        self._set_status("Preset reapplied.")

    def _on_apply_clicked(self) -> None:
        try:
            speed_min = max(0.001, float(self._speed_min_model.get_value_as_float()))
            speed_max = max(speed_min, float(self._speed_max_model.get_value_as_float()))
            speed = float(self._speed_model.get_value_as_float())
            speed = max(speed_min, min(speed, speed_max))

            self._settings.set(CAM_VELOCITY_MIN, speed_min)
            self._settings.set(CAM_VELOCITY_MAX, speed_max)
            self._settings.set(CAM_MOVE_VELOCITY, speed)

            move_accel = max(1.0, float(self._move_accel_model.get_value_as_float()))
            fly_damp = max(0.1, float(self._fly_damp_model.get_value_as_float()))
            self._settings.set(MOVE_ACCEL, move_accel)
            self._settings.set(FLY_DAMP, fly_damp)

            # Keep these asserted after applying any tuning values.
            self._settings.set(CURRENT_TOOL, "navigation")
            self._settings.set(ACTIVE_OPERATION, "fly")
            self._settings.set(DEFAULT_NAV_OPERATION, "fly")
            self._settings.set(CAM_CONTEXT_MENU, False)

            # Keep these camera manipulator values coherent for smooth fly movement.
            self._settings.set(MOVE_DAMP, fly_damp)
            self._settings.set(FLY_ACCEL, move_accel)

            self._set_status("Applied.")
        except Exception as exc:
            self._set_status(f"Apply failed: {exc}")
