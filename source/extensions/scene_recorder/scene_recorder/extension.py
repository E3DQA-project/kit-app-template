"""Scene Recorder Extension — IExt entry point and UI.

Two-panel UI:
  1. Record Camera Path  — capture live navigation simultaneously as a
                           trajectory JSON *and* a viewport PNG sequence,
                           then assemble into video with ffmpeg.
  2. Replay Trajectory   — load a saved JSON, bake into the current scene,
                           set timeline, export video.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import omni.ext
import omni.ui as ui
import omni.log

from .camera_recorder import CameraRecorder
from . import trajectory_utils as tutils

# Optional file-picker import (may be absent in minimal Kit builds).
try:
    from omni.kit.window.filepicker import FilePickerDialog as _FilePickerDialog
    _HAS_FILEPICKER = True
except ImportError:
    _HAS_FILEPICKER = False


# ---------------------------------------------------------------------------
# Extension
# ---------------------------------------------------------------------------

class SceneRecorderExtension(omni.ext.IExt):
    def on_startup(self, _ext_id: str) -> None:
        self._recorder: CameraRecorder = CameraRecorder(sample_fps=30.0)
        self._loaded_trajectory: Optional[Dict[str, Any]] = None
        self._baked_cam_path: Optional[str] = None
        self._picker: Optional[Any] = None

        # In-memory state set after a recording session ends.
        self._in_memory_trajectory: List[Dict[str, Any]] = []
        self._in_memory_fps: float = 30.0
        self._in_memory_frame_paths: List[str] = []

        # --- UI models ---------------------------------------------------
        self._rec_fps_model = ui.SimpleIntModel(30)
        self._rec_capture_video_model = ui.SimpleBoolModel(True)
        self._rec_json_path_model = ui.SimpleStringModel(
            os.path.expanduser("~/trajectory_recording.json")
        )
        self._rec_frames_dir_model = ui.SimpleStringModel(
            os.path.expanduser("~/scene_recorder_frames")
        )
        self._rec_video_path_model = ui.SimpleStringModel(
            os.path.expanduser("~/trajectory_recording.mp4")
        )
        self._replay_json_path_model = ui.SimpleStringModel("")
        self._replay_video_path_model = ui.SimpleStringModel(
            os.path.expanduser("~/trajectory_replay.mp4")
        )

        self._window = ui.Window("Scene Recorder", width=480, height=0)
        self._build_ui()

    def on_shutdown(self) -> None:
        if self._recorder.is_recording:
            self._recorder.discard()
        self._picker = None
        self._window = None

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        with self._window.frame:
            with ui.VStack(spacing=4, height=0):

                # ── Section 1: Record ──────────────────────────────────
                with ui.CollapsableFrame("Record Camera Path", height=0, collapsed=False):
                    with ui.VStack(spacing=6, height=0):
                        ui.Spacer(height=4)

                        # Status
                        with ui.HStack(height=0, spacing=6):
                            ui.Label("Status:", width=60)
                            self._rec_status_label = ui.Label(
                                "Idle",
                                word_wrap=False,
                                style={"color": 0xFFAAAAAA},
                            )

                        # Settings row
                        with ui.HStack(height=0, spacing=6):
                            ui.Label("Sample Rate (fps):", width=130)
                            ui.IntField(
                                self._rec_fps_model, width=55,
                                tooltip="Camera poses (and video frames) to capture per second.",
                            )
                            ui.Spacer(width=10)
                            ui.CheckBox(
                                self._rec_capture_video_model,
                                tooltip="Also capture viewport frames for video export.",
                            )
                            ui.Label(
                                "Capture video simultaneously",
                                tooltip="When checked, viewport frames are saved as PNGs during recording.",
                            )

                        # Frames temp dir (shown only when capture_video is on)
                        with ui.HStack(height=0, spacing=4):
                            ui.Label("Frames folder:", width=100)
                            ui.StringField(
                                self._rec_frames_dir_model,
                                width=ui.Fraction(1),
                                tooltip="Temporary folder for PNG frames (created automatically).",
                            )
                            ui.Button(
                                "...", width=30, height=24,
                                clicked_fn=lambda: self._open_save_picker(
                                    self._rec_frames_dir_model,
                                    title="Select Frames Folder",
                                ),
                            )

                        # Start / Stop
                        with ui.HStack(height=0, spacing=6):
                            self._btn_start_rec = ui.Button(
                                "Start Recording",
                                height=30,
                                clicked_fn=self._on_start_recording,
                                tooltip="Begin sampling camera pose (and optionally capturing frames).",
                            )
                            self._btn_stop_rec = ui.Button(
                                "Stop Recording",
                                height=30,
                                clicked_fn=self._on_stop_recording,
                                enabled=False,
                                tooltip="Stop recording and keep data in memory.",
                            )

                        ui.Separator()

                        # JSON save
                        ui.Label("Save Trajectory JSON:", style={"color": 0xFFCCCCCC})
                        with ui.HStack(height=0, spacing=4):
                            ui.StringField(
                                self._rec_json_path_model,
                                width=ui.Fraction(1),
                                tooltip="Output path for the trajectory JSON file.",
                            )
                            ui.Button(
                                "...", width=30, height=24,
                                clicked_fn=lambda: self._open_save_picker(
                                    self._rec_json_path_model,
                                    title="Save Trajectory JSON",
                                ),
                            )
                        ui.Button(
                            "Save Trajectory JSON",
                            height=28,
                            clicked_fn=self._on_save_json,
                            tooltip="Write the in-memory trajectory to the JSON path above.",
                        )

                        ui.Separator()

                        # Video assembly
                        ui.Label(
                            "Assemble Video from captured frames:",
                            style={"color": 0xFFCCCCCC},
                        )
                        with ui.HStack(height=0, spacing=4):
                            ui.StringField(
                                self._rec_video_path_model,
                                width=ui.Fraction(1),
                                tooltip="Output .mp4 path.",
                            )
                            ui.Button(
                                "...", width=30, height=24,
                                clicked_fn=lambda: self._open_save_picker(
                                    self._rec_video_path_model,
                                    title="Save Recording Video",
                                ),
                            )
                        ui.Button(
                            "Assemble Recording Video",
                            height=28,
                            clicked_fn=self._on_assemble_recording_video,
                            tooltip=(
                                "Run ffmpeg to assemble the captured PNG frames "
                                "into the video file above."
                            ),
                        )

                        self._rec_info_label = ui.Label(
                            "",
                            word_wrap=True,
                            style={"color": 0xFF88CCFF},
                        )
                        ui.Spacer(height=4)

                # ── Section 2: Replay ──────────────────────────────────
                with ui.CollapsableFrame("Replay Trajectory", height=0, collapsed=False):
                    with ui.VStack(spacing=6, height=0):
                        ui.Spacer(height=4)

                        ui.Label("Trajectory JSON:", style={"color": 0xFFCCCCCC})
                        with ui.HStack(height=0, spacing=4):
                            ui.StringField(
                                self._replay_json_path_model,
                                width=ui.Fraction(1),
                                tooltip="Path to a previously saved trajectory JSON file.",
                            )
                            ui.Button(
                                "...", width=30, height=24,
                                clicked_fn=lambda: self._open_load_picker(
                                    self._replay_json_path_model,
                                    title="Open Trajectory JSON",
                                ),
                            )
                        ui.Button(
                            "Load Trajectory",
                            height=28,
                            clicked_fn=self._on_load_trajectory,
                            tooltip="Parse the JSON and display metadata.",
                        )

                        self._replay_status_label = ui.Label(
                            "No trajectory loaded.",
                            word_wrap=True,
                            style={"color": 0xFFAAAAAA},
                        )

                        ui.Separator()

                        ui.Button(
                            "Setup Replay in Scene",
                            height=28,
                            clicked_fn=self._on_setup_replay,
                            tooltip=(
                                "Bake the trajectory as a /RecorderCamera USD animated camera, "
                                "activate it in the viewport, and set the timeline range. "
                                "Press Play on the timeline to preview."
                            ),
                        )

                        ui.Separator()

                        ui.Label("Export Replay as Video:", style={"color": 0xFFCCCCCC})
                        with ui.HStack(height=0, spacing=4):
                            ui.StringField(
                                self._replay_video_path_model,
                                width=ui.Fraction(1),
                                tooltip="Output .mp4 path for the replay video.",
                            )
                            ui.Button(
                                "...", width=30, height=24,
                                clicked_fn=lambda: self._open_save_picker(
                                    self._replay_video_path_model,
                                    title="Save Replay Video",
                                ),
                            )
                        ui.Button(
                            "Capture & Export Replay Video",
                            height=28,
                            clicked_fn=self._on_export_replay_video,
                            tooltip=(
                                "Play the timeline while capturing viewport frames, "
                                "then assemble into the video file above via ffmpeg."
                            ),
                        )

                        self._replay_info_label = ui.Label(
                            "",
                            word_wrap=True,
                            style={"color": 0xFF88CCFF},
                        )
                        ui.Spacer(height=4)

    # ------------------------------------------------------------------
    # Record callbacks
    # ------------------------------------------------------------------

    def _on_start_recording(self) -> None:
        fps = max(1, min(120, self._rec_fps_model.get_value_as_int()))
        capture_video = self._rec_capture_video_model.get_value_as_bool()
        frames_dir = self._rec_frames_dir_model.get_value_as_string().strip()

        self._recorder = CameraRecorder(
            sample_fps=float(fps),
            capture_video=capture_video,
            frames_dir=frames_dir,
        )
        self._recorder.start(on_frame_cb=self._on_record_frame)
        self._btn_start_rec.enabled = False
        self._btn_stop_rec.enabled = True

        status = f"Recording @ {fps} fps"
        if capture_video:
            status += " + video frames"
        self._set_rec_status(status + "…")
        self._set_rec_info("")

    def _on_stop_recording(self) -> None:
        trajectory, frame_paths = self._recorder.stop()
        self._btn_start_rec.enabled = True
        self._btn_stop_rec.enabled = False

        fps = self._recorder.sample_fps
        n = len(trajectory)
        dur = n / fps if fps > 0 else 0.0

        self._in_memory_trajectory = trajectory
        self._in_memory_fps = fps
        self._in_memory_frame_paths = frame_paths

        info_parts = [f"{n} pose frames @ {fps:.0f} fps ({dur:.1f} s)"]
        if frame_paths:
            info_parts.append(
                f"{len(frame_paths)} video frames saved to:\n"
                f"{self._recorder.frames_dir}"
            )
            info_parts.append("Click 'Assemble Recording Video' to encode.")
        else:
            info_parts.append("Video capture was off — only JSON is available.")

        self._set_rec_status(f"Stopped — {n} frames @ {fps:.0f} fps ({dur:.1f} s)")
        self._set_rec_info("\n".join(info_parts))

    def _on_record_frame(self, frame_count: int) -> None:
        self._set_rec_status(
            f"Recording… {frame_count} frames"
        )

    def _on_save_json(self) -> None:
        traj = self._in_memory_trajectory
        if not traj:
            self._set_rec_info("No trajectory in memory. Record first.")
            return
        path = self._rec_json_path_model.get_value_as_string().strip()
        if not path:
            self._set_rec_info("Enter an output JSON path first.")
            return
        fps = self._in_memory_fps
        source_scene = self._current_stage_url()
        try:
            tutils.save_trajectory(traj, fps, source_scene, path)
            self._set_rec_info(f"Saved {len(traj)} frames to:\n{path}")
        except Exception as exc:
            self._set_rec_info(f"Save failed: {exc}")
            omni.log.error(f"[scene_recorder] save_trajectory: {exc}")

    def _on_assemble_recording_video(self) -> None:
        frame_paths = self._in_memory_frame_paths
        if not frame_paths:
            self._set_rec_info(
                "No video frames in memory.\n"
                "Enable 'Capture video simultaneously' before recording."
            )
            return
        video_path = self._rec_video_path_model.get_value_as_string().strip()
        if not video_path:
            self._set_rec_info("Enter an output video path first.")
            return
        frames_dir = self._recorder.frames_dir
        fps = self._in_memory_fps

        self._set_rec_info(f"Assembling {len(frame_paths)} frames with ffmpeg…")
        ok = tutils.assemble_video_from_frames(frames_dir, fps, video_path)
        if ok:
            self._set_rec_info(f"Video saved to:\n{video_path}")
        else:
            self._set_rec_info(
                "ffmpeg assembly failed. Check the log for details.\n"
                "(Make sure ffmpeg is installed and on PATH.)"
            )

    # ------------------------------------------------------------------
    # Replay callbacks
    # ------------------------------------------------------------------

    def _on_load_trajectory(self) -> None:
        path = self._replay_json_path_model.get_value_as_string().strip()
        if not path:
            self._set_replay_status("Enter a trajectory JSON path first.")
            return
        try:
            data = tutils.load_trajectory(path)
            self._loaded_trajectory = data
            self._baked_cam_path = None
            fps = float(data.get("fps", 30.0))
            n = int(data.get("total_frames", len(data.get("trajectory", []))))
            dur = n / fps if fps > 0 else 0.0
            src = data.get("source_scene", "(unknown)")
            self._set_replay_status(
                f"Loaded: {n} frames @ {fps:.0f} fps ({dur:.1f} s)\n"
                f"Source: {os.path.basename(src)}"
            )
            self._set_replay_info("")
        except Exception as exc:
            self._set_replay_status(f"Load failed: {exc}")
            omni.log.error(f"[scene_recorder] load_trajectory: {exc}")

    def _on_setup_replay(self) -> None:
        if self._loaded_trajectory is None:
            self._set_replay_info("Load a trajectory JSON first.")
            return
        stage = self._get_stage()
        if stage is None:
            self._set_replay_info("No stage open. Open a USD scene first.")
            return

        baked = tutils.bake_trajectory_to_usd(self._loaded_trajectory, stage)
        if baked is None:
            self._set_replay_info("Baking to USD failed. Check the log.")
            return

        fps = float(self._loaded_trajectory.get("fps", 30.0))
        total = int(
            self._loaded_trajectory.get(
                "total_frames",
                len(self._loaded_trajectory.get("trajectory", [])),
            )
        )
        tutils.activate_recorder_camera(stage, baked)
        tutils.set_timeline_range(fps, total)
        self._baked_cam_path = baked
        self._set_replay_info(
            f"Replay ready: {total} frames @ {fps:.0f} fps.\n"
            f"Camera prim: {baked}\n"
            "Press Play on the timeline to preview the path."
        )

    def _on_export_replay_video(self) -> None:
        if self._loaded_trajectory is None:
            self._set_replay_info("Load and set up a trajectory first.")
            return

        stage = self._get_stage()
        if stage is None:
            self._set_replay_info("No stage open.")
            return

        # Bake on demand if not done yet.
        if self._baked_cam_path is None:
            self._on_setup_replay()
            if self._baked_cam_path is None:
                return

        video_path = self._replay_video_path_model.get_value_as_string().strip()
        if not video_path:
            self._set_replay_info("Enter an output video path first.")
            return

        fps = float(self._loaded_trajectory.get("fps", 30.0))
        total = int(
            self._loaded_trajectory.get(
                "total_frames",
                len(self._loaded_trajectory.get("trajectory", [])),
            )
        )

        # Derive a temporary frames folder from the video path.
        video_stem = os.path.splitext(video_path)[0]
        frames_dir = video_stem + "_frames"

        self._set_replay_info("Starting replay frame capture…")
        ok = self._capture_replay_frames(fps, total, frames_dir)
        if not ok:
            self._set_replay_info(
                "Frame capture could not be started programmatically.\n"
                "Play the timeline manually while 'Capture video simultaneously' "
                "is on in the Record section as a workaround."
            )
            return

        self._set_replay_info(f"Assembling {total} frames with ffmpeg…")
        assembled = tutils.assemble_video_from_frames(frames_dir, fps, video_path)
        if assembled:
            self._set_replay_info(f"Replay video saved to:\n{video_path}")
        else:
            self._set_replay_info(
                "ffmpeg assembly failed. Check the log.\n"
                f"Raw frames are in: {frames_dir}"
            )

    def _capture_replay_frames(
        self, fps: float, total_frames: int, frames_dir: str
    ) -> bool:
        """Drive the timeline frame-by-frame and capture each rendered frame.

        Returns True when all frames were queued, False if the capture
        interface was not available.
        """
        try:
            import omni.renderer_capture as rc
            import omni.kit.app
            import omni.timeline

            capture = rc.acquire_renderer_capture_interface()
            if capture is None:
                return False

            os.makedirs(frames_dir, exist_ok=True)
            tl = omni.timeline.get_timeline_interface()
            app = omni.kit.app.get_app()

            for idx in range(total_frames):
                time_s = idx / fps
                tl.set_current_time(time_s)
                # Let the engine render one frame at the new time.
                app.update()
                frame_path = os.path.join(frames_dir, f"frame_{idx:06d}.png")
                capture.capture_next_frame_swapchain_to_file(frame_path)
                # Pump once more so the capture actually fires.
                app.update()

            return True

        except Exception as exc:
            _warn(f"_capture_replay_frames failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # File-picker helpers
    # ------------------------------------------------------------------

    def _open_save_picker(
        self,
        target_model: ui.SimpleStringModel,
        title: str = "Save File",
    ) -> None:
        if not _HAS_FILEPICKER:
            self._set_rec_info("FilePickerDialog not available; type path manually.")
            return
        self._picker = _FilePickerDialog(
            title=title,
            apply_button_label="Select",
            click_apply_handler=lambda path, _: self._on_picker_apply(path, target_model),
            click_cancel_handler=lambda _: self._on_picker_cancel(),
        )
        self._picker.show(os.path.dirname(target_model.get_value_as_string()))

    def _open_load_picker(
        self,
        target_model: ui.SimpleStringModel,
        title: str = "Open File",
    ) -> None:
        if not _HAS_FILEPICKER:
            self._set_replay_info("FilePickerDialog not available; type path manually.")
            return
        self._picker = _FilePickerDialog(
            title=title,
            apply_button_label="Open",
            click_apply_handler=lambda path, _: self._on_picker_apply(path, target_model),
            click_cancel_handler=lambda _: self._on_picker_cancel(),
        )
        self._picker.show(os.path.dirname(target_model.get_value_as_string()))

    def _on_picker_apply(self, path: str, target_model: ui.SimpleStringModel) -> None:
        if path:
            target_model.set_value(path)
        if self._picker is not None:
            self._picker.hide()

    def _on_picker_cancel(self) -> None:
        if self._picker is not None:
            self._picker.hide()

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def _set_rec_status(self, msg: str) -> None:
        try:
            self._rec_status_label.text = msg
        except Exception:
            pass

    def _set_rec_info(self, msg: str) -> None:
        try:
            self._rec_info_label.text = msg
        except Exception:
            pass

    def _set_replay_status(self, msg: str) -> None:
        try:
            self._replay_status_label.text = msg
        except Exception:
            pass

    def _set_replay_info(self, msg: str) -> None:
        try:
            self._replay_info_label.text = msg
        except Exception:
            pass

    def _get_stage(self):
        try:
            import omni.usd
            return omni.usd.get_context().get_stage()
        except Exception:
            return None

    def _current_stage_url(self) -> str:
        try:
            import omni.usd
            return omni.usd.get_context().get_stage_url() or ""
        except Exception:
            return ""


def _warn(msg: str) -> None:
    try:
        omni.log.warn(f"[scene_recorder] {msg}")
    except Exception:
        print(f"[scene_recorder] WARN: {msg}")
