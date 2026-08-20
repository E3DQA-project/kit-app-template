# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import asyncio
import os

import carb
import carb.events
import carb.tokens
from carb.eventdispatcher import get_eventdispatcher

import omni.client
import omni.kit.app
import omni.kit.livestream.messaging as messaging
import omni.usd

from .stream_diagnostics import (
    _ActivityCaptureGate,
    _LoadingStatusGate,
    _NvtxRangeGate,
    _begin_nvtx_range,
    _end_nvtx_range,
    _StreamDiagnostics,
    _StreamingStateGate,
)


class LoadingManager:
    """Manages the loading of USD stages and sends messages to the client"""
    def __init__(self):
        self._subscriptions = []  # Holds subscription pointers

        # -- state variables
        # URL of stage load request. Can be used in messaging with client.
        self._requested_stage_url: str = ""
        self._stage_is_opening: bool = False

        # URL of loaded stage. Should not be used in messaging with client
        # because it may reveal directory paths in environment where
        # application runs.
        self._opened_stage_url: str = ""
        self._stage_has_opened = False
        self._streaming_manager_is_busy: bool = False

        # States if opened stage is opened from storage as in not a
        # new unsaved stage
        self._persisted_stage: bool = False
        self._is_evaluating_loading_status: bool = False
        self._stream_generation = 0
        self._stream_diag = None
        self._streaming_state_gate = _StreamingStateGate()
        self._loading_status_gate = _LoadingStatusGate()
        self._activity_capture_gate = _ActivityCaptureGate()
        self._activity_profiler = None
        self._activity_profiler_module = None
        self._nvtx_range_gate = _NvtxRangeGate()
        self._nvtx_profiler = None

        # -- register outgoing events/messages
        outgoing = [
            "openedStageResult",  # notify when USD Stage has loaded.
            "updateProgressAmount",  # Status bar event denoting progress
            "updateProgressActivity",  # Status bar event denoting activity
            "loadingStateResponse",  # Response to loadingStateQuery
        ]

        for o in outgoing:
            messaging.register_event_type_to_send(o)
            omni.kit.app.register_event_alias(
                carb.events.type_from_string(o),
                o,
            )

        # -- register incoming events/messages
        incoming = {
            'openStageRequest': self._on_open_stage,  # request to open a stage
            # internal event to capture progress status
            "omni.kit.window.status_bar@progress": self._on_progress,
            # internal event to capture progress activity
            "omni.kit.window.status_bar@activity": self._on_activity,
            "loadingStateQuery": self._on_load_state_query,
        }
        ed = get_eventdispatcher()
        for event_type, handler in incoming.items():
            # Registering event aliases for incoming events that now leverage Events 2.0
            # TODO: Remove this when all clients have migrated to Events 2.0
            # This is a temporary solution to ensure compatibility with existing clients
            omni.kit.app.register_event_alias(
                carb.events.type_from_string(event_type),
                event_type,
            )
            self._subscriptions.append(
                ed.observe_event(
                    observer_name=f"LoadingManager:{event_type}",
                    event_name=event_type,
                    on_event=handler
                )
            )
        usd_context = omni.usd.get_context()
        # -- subscribe to stage events
        self._subscriptions.extend([
            ed.observe_event(
                observer_name="LoadingManager:stage:opening",
                event_name=usd_context.stage_event_name(omni.usd.StageEventType.OPENING),
                on_event=self._on_stage_event_opening,
            ),
            ed.observe_event(
                observer_name="LoadingManager:stage:assets_loading",
                event_name=usd_context.stage_event_name(omni.usd.StageEventType.ASSETS_LOADING),
                on_event=self._on_stage_event_assets_loading,
            ),
            ed.observe_event(
                observer_name="LoadingManager:stage:assets_loaded",
                event_name=usd_context.stage_event_name(omni.usd.StageEventType.ASSETS_LOADED),
                on_event=self._on_stage_event_assets_loaded,
            ),
            ed.observe_event(
                observer_name="LoadingManager:stage:geostreaming_started",
                event_name=usd_context.stage_event_name(omni.usd.StageEventType.HYDRA_GEOSTREAMING_STARTED),
                on_event=lambda _event: self._record_stream_event("GEOSTREAMING_STARTED"),
            ),
            ed.observe_event(
                observer_name="LoadingManager:stage:geostreaming_stopped",
                event_name=usd_context.stage_event_name(omni.usd.StageEventType.HYDRA_GEOSTREAMING_STOPPED),
                on_event=lambda _event: self._record_stream_event("GEOSTREAMING_STOPPED"),
            ),
            ed.observe_event(
                observer_name="LoadingManager:stage:geostreaming_memory",
                event_name=usd_context.stage_event_name(omni.usd.StageEventType.HYDRA_GEOSTREAMING_STOPPED_NOT_ENOUGH_MEM),
                on_event=lambda _event: self._record_stream_event("GEOSTREAMING_STOPPED_NOT_ENOUGH_MEM"),
            ),
            ed.observe_event(
                observer_name="LoadingManager:stage:geostreaming_limit",
                event_name=usd_context.stage_event_name(omni.usd.StageEventType.HYDRA_GEOSTREAMING_STOPPED_AT_LIMIT),
                on_event=lambda _event: self._record_stream_event("GEOSTREAMING_STOPPED_AT_LIMIT"),
            ),
        ])

        self._subscriptions.append(
            ed.observe_event(
                observer_name="LoadingManager:stage:streaming_status",
                event_name="omni.streamingstatus:streaming_status",
                on_event=self._on_rxt_streaming_event,
            )
        )

    def _record_stream_event(self, event: str, **fields) -> None:
        if self._stream_diag is not None:
            self._stream_diag.record(event, **fields)

    def _scene_loading_activity_capture_is_enabled(self) -> bool:
        try:
            return carb.settings.get_settings().get_as_bool(
                "/exts/nycu.my_usd_viewer_messaging_extension/sceneLoadingActivityCapture"
            )
        except Exception:
            return False

    def _scene_loading_nvtx_capture_is_enabled(self) -> bool:
        try:
            return carb.settings.get_settings().get_as_bool(
                "/exts/nycu.my_usd_viewer_messaging_extension/sceneLoadingNvtxCapture"
            )
        except Exception:
            return False

    def _begin_scene_loading_nvtx_capture(self) -> None:
        if not self._persisted_stage or not self._scene_loading_nvtx_capture_is_enabled():
            return
        try:
            import carb.profiler as profiler

            if _begin_nvtx_range(self._nvtx_range_gate, profiler, "MOS_SCENE_ASSETS_LOADING"):
                self._nvtx_profiler = profiler
                self._record_stream_event("NVTX_SCENE_LOADING_RANGE_STARTED")
        except Exception as exc:
            self._record_stream_event("NVTX_CAPTURE_UNAVAILABLE", error=type(exc).__name__)

    def _end_scene_loading_nvtx_capture(self) -> None:
        profiler = self._nvtx_profiler
        self._nvtx_profiler = None
        if profiler is None:
            return
        try:
            if _end_nvtx_range(self._nvtx_range_gate, profiler):
                self._record_stream_event("NVTX_SCENE_LOADING_RANGE_STOPPED")
        except Exception as exc:
            self._record_stream_event("NVTX_CAPTURE_UNAVAILABLE", error=type(exc).__name__)

    def _begin_scene_loading_activity_capture(self) -> None:
        if not self._persisted_stage or not self._scene_loading_activity_capture_is_enabled():
            return
        try:
            import omni.activity.profiler as activity_profiler
        except ImportError:
            self._record_stream_event("ACTIVITY_CAPTURE_UNAVAILABLE", reason="extension_not_enabled")
            return
        profiler = None
        try:
            profiler = activity_profiler.acquire_activity_profiler(
                plugin_name="omni.activity.profiler.plugin"
            )
            if not self._activity_capture_gate.begin(
                lambda: profiler.enable_capture_mask(activity_profiler.CAPTURE_MASK_SCENE_LOADING)
            ):
                activity_profiler.release_activity_profiler(profiler)
                return
            self._activity_profiler = profiler
            self._activity_profiler_module = activity_profiler
            self._record_stream_event("ACTIVITY_SCENE_LOADING_CAPTURE_STARTED")
        except Exception as exc:
            if profiler is not None:
                activity_profiler.release_activity_profiler(profiler)
            self._record_stream_event("ACTIVITY_CAPTURE_UNAVAILABLE", error=type(exc).__name__)

    def _end_scene_loading_activity_capture(self) -> None:
        profiler = self._activity_profiler
        activity_profiler = self._activity_profiler_module
        self._activity_profiler = None
        self._activity_profiler_module = None
        if profiler is None or activity_profiler is None:
            return
        try:
            if self._activity_capture_gate.end(profiler.disable_capture_mask):
                self._record_stream_event("ACTIVITY_SCENE_LOADING_CAPTURE_STOPPED")
        finally:
            activity_profiler.release_activity_profiler(profiler)

    def _record_loading_status(self) -> None:
        try:
            message, files_loaded, total_files = omni.usd.get_context().get_stage_loading_status()
            if self._loading_status_gate.observe(message, files_loaded, total_files):
                self._record_stream_event(
                    "STAGE_LOADING_STATUS", message=repr(message),
                    files_loaded=files_loaded, total_files=total_files,
                )
        except Exception as exc:
            self._record_stream_event("STAGE_LOADING_STATUS_UNAVAILABLE", error=type(exc).__name__)

    def _on_load_state_query(self, event: carb.events.IEvent) -> None:
        payload = {"loading_state": "idle", "url": self._opened_stage_url}
        if self._stage_is_opening:
            payload = { "loading_state": "busy", "url": self._requested_stage_url }
        elif self._stage_has_opened:
            payload = { "loading_state": "idle", "url": self._requested_stage_url }

        get_eventdispatcher().dispatch_event("loadingStateResponse", payload=payload)


    def _on_open_stage(self, event: carb.events.IEvent) -> None:
        """
        Handler for `openStageRequest` event.

        Starts loading a given URL, will send success if the layer is already
        loaded, and an error on any failure.
        """

        if "url" not in event.payload:
            carb.log_error(
                f"Unexpected message payload: missing \"url\" key. Payload: '{event.payload}'")
            return

        self._requested_stage_url = event.payload["url"]
        carb.log_info(
            f"Received message to load '{self._requested_stage_url}'"
        )

        def process_url(url):
            # Using a single leading `.` to signify that the path is relative to the ${app} token's parent directory
            # Because we've moved the samples out of the app directory, we need to check for that here
            # in the samples extension directory.
            # If that doesn't exist (using older version of the extension), we fall back to old behavior.
            if url.startswith(("./", ".\\")):
                if url.startswith(("./samples", ".\\samples")):
                    sample_url = carb.tokens.acquire_tokens_interface().resolve(
                        "${omni.usd_viewer.samples}/" + url[1:].replace("samples", "samples_data")
                    )
                    if os.path.exists(sample_url):
                        return sample_url
                return carb.tokens.acquire_tokens_interface().resolve(
                    "${app}/.." + url[1:]
                )
            return carb.tokens.acquire_tokens_interface().resolve(url)

        # Check to see if we've already loaded the current stage.
        url = process_url(self._requested_stage_url)

        self._end_scene_loading_activity_capture()
        self._end_scene_loading_nvtx_capture()
        stage = omni.usd.get_context().get_stage()
        current_stage = stage.GetRootLayer().identifier if stage else ''

        # If we are, we don't need to reload the file, instead we'll just send the success message.
        if omni.client.utils.equal_urls(url, current_stage):
            carb.log_info(f'Client requested to open a stage that is already open: {url}')
            payload = {"url": self._requested_stage_url, "result": "success", "error": ''}
            get_eventdispatcher().dispatch_event("openedStageResult", payload=payload)
            self._reset_state()
            return

        # Asynchronously load the incoming stage
        async def open_stage():
            carb.log_info(f'Opening stage per client request: {url}')
            usd_context = omni.usd.get_context()
            if url:
                result, error = await usd_context.open_stage_async(url, omni.usd.UsdContextInitialLoadSet.LOAD_ALL)
            else:
                result, error = await usd_context.new_stage_async()

            if result is not True:
                # Send message to client that loading failed.
                carb.log_warn(f'The file that the client requested failed to load: {url} (error: {error})')
                payload = {"url": url, "result": "error", "error": error}
                get_eventdispatcher().dispatch_event("openedStageResult", payload=payload)
                self._reset_state()
                return

        asyncio.ensure_future(open_stage())

    def _on_stage_event_opening(self, event) -> None:
        """Manage extension state via the stage event stream.
        When a new stage is open we reload the data model and
        set the state for the UI.

        Args:
            event (carb.events.IEvent): Event type
        """
        self._stage_is_opening = True
        payload: dict = dict(event.payload)
        if 'val' in payload.keys():
            self._opened_stage_url = payload['val']
        else:
            self._opened_stage_url = ''
        self._persisted_stage = True if self._opened_stage_url else False
        self._stream_generation += 1
        self._stream_diag = _StreamDiagnostics(self._stream_generation, self._opened_stage_url)
        self._streaming_state_gate = _StreamingStateGate()
        self._loading_status_gate = _LoadingStatusGate()
        self._record_stream_event("USD_OPENING", persisted=self._persisted_stage)
        return

    def _on_stage_event_assets_loading(self, _event) -> None:
        if self._stage_is_opening:
            self._record_stream_event("USD_ASSETS_LOADING")
            self._begin_scene_loading_activity_capture()
            self._begin_scene_loading_nvtx_capture()

    def _on_stage_event_assets_loaded(self, event) -> None:
        """Manage extension state via the stage event stream.
        When a new stage is open we reload the data model and
        set the state for the UI.

        Args:
            event (carb.events.IEvent): Event type
        """
        # Check that a stage is opening. Assets can load after stage has opened.
        if not self._stage_is_opening:
            return
        self._stage_is_opening = False
        self._stage_has_opened = True
        self._record_stream_event("USD_ASSETS_LOADED")
        self._end_scene_loading_activity_capture()
        self._end_scene_loading_nvtx_capture()
        self._record_loading_status()

        # Async call to evaluate opened state
        asyncio.ensure_future(self._evaluate_load_status())
        return

    def _on_rxt_streaming_event(self, event) -> None:
        """
        Notes streaming manager's busy state

        Args:
            event (carb.events.IEvent): Contains payload sender and type -
            https://docs.omniverse.nvidia.com/kit/docs/kit-manual/105.0/carb.events/carb.events.IEvent.html
        """
        self._streaming_manager_is_busy = bool(event.payload['isBusy'])
        transition = self._streaming_state_gate.observe(self._streaming_manager_is_busy)
        if transition is not None:
            self._record_stream_event(transition, signal="omni.streamingstatus")

    async def _evaluate_load_status(self):
        """
        If streaming manager is not busy and the stage is loaded from storage,
        notify the client.
        """
        # Only evaluate for stage loaded from storage.
        if not self._persisted_stage:
            return

        if self._is_evaluating_loading_status:
            return
        self._is_evaluating_loading_status = True

        # Wait until all dependencies have loaded by streaming manager.
        while self._streaming_manager_is_busy or not self._stage_has_opened:
            self._record_loading_status()
            await omni.kit.app.get_app().next_update_async()

        self._record_loading_status()
        self._record_stream_event("STREAMING_GATE_CLEAR")
        for update_number in range(1, 3):
            await omni.kit.app.get_app().next_update_async()
            self._record_stream_event(f"POST_STREAMING_UPDATE_{update_number}")

        # Stage has loaded with all dependencies. Send message to client.
        url = self._requested_stage_url if self._requested_stage_url  else '[obfuscated]'
        carb.log_info(
            f'Sending message to client that stage has loaded: {url}'
        )
        self._record_stream_event("VIEWER_STAGE_LOADED")
        payload = {"url": url, "result": "success", "error": ''}
        get_eventdispatcher().dispatch_event("openedStageResult", payload=payload)

        # reset
        self._is_evaluating_loading_status = False
        self._reset_state()

    def _on_progress(self, event: carb.events.IEvent):
        """
        Handler for `omni.kit.window.status_bar@progress` event.
        This forwards the statusbar progress events to the streaming client.
        """
        # Only notify for stage loaded from storage.
        if not self._persisted_stage:
            return

        # Send progress message
        carb.log_info('Sending message to client about loading progress.')
        self._record_stream_event("STREAMING_PROGRESS", payload=repr(dict(event.payload)))
        get_eventdispatcher().dispatch_event("updateProgressAmount", payload=dict(event.payload))

    def _on_activity(self, event: carb.events.IEvent):
        """
        Handler for `omni.kit.window.status_bar@activity` event.
        This forwards the statusbar activity events to the streaming client.
        """
        # Only notify for stage loaded from storage.
        if not self._persisted_stage:
            return

        carb.log_info('Storing message about loading activity.')
        self._record_stream_event("STREAMING_ACTIVITY", payload=repr(dict(event.payload)))
        # Send activity message
        carb.log_info('Sending message to client about loading activity.')
        get_eventdispatcher().dispatch_event("updateProgressActivity", payload=dict(event.payload))

    def on_shutdown(self) -> None:
        """
        Clean up subscriptions
        """
        self._end_scene_loading_activity_capture()
        self._end_scene_loading_nvtx_capture()
        if self._subscriptions:
            self._subscriptions.clear()

    def _reset_state(self):
        """
        Reset the internal state - ready for new stage to be loaded
        """
        self._end_scene_loading_activity_capture()
        self._end_scene_loading_nvtx_capture()
        stage = omni.usd.get_context().get_stage()
        self._requested_stage_url = ""
        self._opened_stage_url = stage.GetRootLayer().identifier if stage else ""
        self._stage_has_opened = False
        self._streaming_manager_is_busy = False
        self._persisted_stage = False
        self._stream_diag = None
