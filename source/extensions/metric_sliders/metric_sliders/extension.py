# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import omni.ext
import omni.ui as ui


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metrics_db_path() -> str:
    # Keep it user-local, not project-local.
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "metric_sliders", "metrics.json")


def _read_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        # Corrupt / unreadable: do not block UI; start fresh.
        return {}


def _write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def get_current_stage_url() -> str:
    """Best-effort: return a stable identifier for the 'currently loaded file'."""
    try:
        import omni.usd

        url = omni.usd.get_context().get_stage_url() or ""
        return url
    except Exception:
        return ""


class MetricSlidersExtension(omni.ext.IExt):
    def on_startup(self, _ext_id: str) -> None:
        self._window = ui.Window("Metric Sliders", width=420, height=240)

        self._models: Dict[str, ui.AbstractValueModel] = {
            "Geometric Consistency": ui.SimpleIntModel(0),
            "Textural Fidelity": ui.SimpleIntModel(0),
            "Volumetric Cleanliness": ui.SimpleIntModel(0),
            "Semantic Context Coherence": ui.SimpleIntModel(0),
        }

        self._subscriptions = []
        self._status_label = None

        with self._window.frame:
            with ui.VStack(spacing=8, height=0):
                ui.Label("Rate the currently loaded file (0–5).", word_wrap=True)

                for title, model in self._models.items():
                    with ui.HStack(spacing=10, height=0):
                        ui.Label(title, width=240, word_wrap=True)
                        ui.IntSlider(model=model, min=0, max=5, width=140)
                        value_label = ui.Label("0", width=30, alignment=ui.Alignment.RIGHT_CENTER)

                        def _make_on_changed(lbl: ui.Label):
                            def _on_changed(m: ui.AbstractValueModel):
                                try:
                                    lbl.text = str(int(m.get_value_as_int()))
                                except Exception:
                                    lbl.text = "0"

                            return _on_changed

                        try:
                            value_label.text = str(int(model.get_value_as_int()))
                            self._subscriptions.append(model.add_value_changed_fn(_make_on_changed(value_label)))
                        except Exception:
                            pass

                with ui.HStack(spacing=10, height=0):
                    ui.Button("Save", width=120, clicked_fn=self._on_save_clicked)
                    self._status_label = ui.Label("", word_wrap=True)

                with ui.HStack(spacing=10, height=0):
                    ui.Button("Load (current file)", width=160, clicked_fn=self._on_load_clicked)
                    ui.Button("Reset to 0", width=120, clicked_fn=self._on_reset_clicked)

        # Try to preload values for the current stage.
        self._on_load_clicked()

    def on_shutdown(self) -> None:
        self._window = None
        self._models = {}
        self._subscriptions = []
        self._status_label = None

    def _set_status(self, msg: str) -> None:
        if self._status_label is not None:
            try:
                self._status_label.text = msg
            except Exception:
                pass

    def _current_key(self) -> str:
        url = get_current_stage_url()
        return url if url else "<no_stage_loaded>"

    def _collect_metrics(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for title, model in self._models.items():
            try:
                out[title] = int(model.get_value_as_int())
            except Exception:
                out[title] = 0
        return out

    def _apply_metrics(self, metrics: Dict[str, Any]) -> None:
        for title, model in self._models.items():
            if title not in metrics:
                continue
            try:
                v = int(metrics[title])
                v = max(0, min(5, v))
                model.set_value(v)
            except Exception:
                continue

    def _on_reset_clicked(self) -> None:
        for model in self._models.values():
            try:
                model.set_value(0)
            except Exception:
                pass
        self._set_status("Reset.")

    def _on_save_clicked(self) -> None:
        key = self._current_key()
        path = _metrics_db_path()
        db = _read_json(path)

        db[key] = {
            "saved_at": _now_iso(),
            "metrics": self._collect_metrics(),
        }

        _write_json(path, db)
        self._set_status(f"Saved for: {key}")

    def _on_load_clicked(self) -> None:
        key = self._current_key()
        path = _metrics_db_path()
        db = _read_json(path)
        entry: Optional[Dict[str, Any]] = db.get(key) if isinstance(db, dict) else None

        if not entry:
            self._set_status(f"No saved metrics for: {key}")
            return

        metrics = entry.get("metrics") if isinstance(entry, dict) else None
        if isinstance(metrics, dict):
            self._apply_metrics(metrics)
            saved_at = entry.get("saved_at", "")
            self._set_status(f"Loaded ({saved_at}) for: {key}")
        else:
            self._set_status(f"Saved entry invalid for: {key}")

