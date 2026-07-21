"""
MOS scene preload — Phase A (disk) + Phase C (GPU-resident dual slots).

Phase A: copy/warm the next USDZ while the participant navigates.
Phase C: keep scene N+1 composed under an invisible sibling prim so Next is a
visibility swap (+ reference clear), not a full open_stage.

Disk-only Mode never helped wall-clock here: local cache hits still paid ~20s
in USD/GPU bring-up. Dual-slot residency targets that cost.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from typing import Optional, Tuple

import carb
import carb.settings
import omni.kit.app
import omni.log
import omni.usd

_EXT_ID = "nycu.mos_app_extension"
_SETTINGS_ROOT = f"/exts/{_EXT_ID}/preload"

_CHUNK_BYTES = 8 * 1024 * 1024
_YIELD_EVERY_CHUNKS = 8

# Wrapper-stage slot prims (session-layer authored).
_SLOT_A = "/World/MosSlotA"
_SLOT_B = "/World/MosSlotB"
_CTX_NAME = ""  # default UsdContext


def _settings() -> carb.settings.ISettings:
    return carb.settings.get_settings()


def _get_bool(key: str, default: bool) -> bool:
    try:
        val = _settings().get(f"{_SETTINGS_ROOT}/{key}")
        if val is None:
            return default
        return bool(val)
    except Exception:
        return default


def _get_str(key: str, default: str) -> str:
    try:
        val = _settings().get_as_string(f"{_SETTINGS_ROOT}/{key}")
        if val is None or val == "":
            return default
        return str(val)
    except Exception:
        return default


def _get_float(key: str, default: float) -> float:
    try:
        val = _settings().get_as_float(f"{_SETTINGS_ROOT}/{key}")
        if val is None:
            return default
        return float(val)
    except Exception:
        return default


def _get_int(key: str, default: int) -> int:
    try:
        val = _settings().get_as_int(f"{_SETTINGS_ROOT}/{key}")
        if val is None:
            return default
        return int(val)
    except Exception:
        return default


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def _cache_filename(src_path: str) -> str:
    abs_src = _norm(src_path)
    digest = hashlib.sha1(abs_src.encode("utf-8")).hexdigest()[:12]
    stem, ext = os.path.splitext(os.path.basename(abs_src))
    if not ext:
        ext = ".usdz"
    return f"{stem}_{digest}{ext}"


def preload_mode() -> str:
    return _get_str("mode", "gpu_resident").strip().lower()


def disk_enabled() -> bool:
    if not _get_bool("enabled", True):
        return False
    return preload_mode() in ("disk", "usd_context", "gpu_resident")


def gpu_resident_enabled() -> bool:
    if not _get_bool("enabled", True):
        return False
    return preload_mode() == "gpu_resident"


# ── Phase A: disk prefetcher ───────────────────────────────────────────────────

class DiskPreloader:
    """Lookahead=1 disk prefetcher for the next MOS USDZ."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._generation: int = 0
        self._target_src: Optional[str] = None
        self._cached_path: Optional[str] = None
        self._status: str = "idle"
        self._error: Optional[str] = None
        self._session_files: set[str] = set()
        self._pinned_open_path: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return disk_enabled()

    def status_for(self, src_path: str) -> str:
        if not src_path or self._target_src is None:
            return "idle"
        if _norm(src_path) != self._target_src:
            return "idle"
        return self._status

    def resolve_open_path(self, src_path: str) -> str:
        src = _norm(src_path)
        if (
            self._status == "ready"
            and self._target_src == src
            and self._cached_path
            and os.path.isfile(self._cached_path)
        ):
            try:
                if os.path.getsize(self._cached_path) == os.path.getsize(src):
                    omni.log.warn(
                        f"[{_EXT_ID}] Preload hit (local cache): "
                        f"{os.path.basename(src)} → {self._cached_path}"
                    )
                    return self._cached_path
            except OSError:
                pass
        if self._status == "ready" and self._target_src == src:
            omni.log.warn(
                f"[{_EXT_ID}] Preload ready (page cache): {os.path.basename(src)}"
            )
        return src_path

    def pin_open_path(self, open_path: str) -> None:
        prev = self._pinned_open_path
        self._pinned_open_path = _norm(open_path) if open_path else None
        if prev and prev != self._pinned_open_path and prev in self._session_files:
            if prev != self._cached_path:
                try:
                    if os.path.isfile(prev):
                        os.remove(prev)
                except OSError:
                    pass
                self._session_files.discard(prev)

    def schedule(self, src_path: Optional[str]) -> None:
        self.cancel()
        if not src_path or not self.enabled:
            return
        if _get_int("lookahead", 1) < 1:
            return

        src = _norm(src_path)
        if not os.path.isfile(src):
            omni.log.warn(f"[{_EXT_ID}] Preload skip — file missing: {src}")
            self._status = "failed"
            self._error = "missing"
            self._target_src = src
            return

        if (
            self._status == "ready"
            and self._target_src == src
            and (
                self._cached_path is None
                or (
                    os.path.isfile(self._cached_path)
                    and os.path.getsize(self._cached_path) == os.path.getsize(src)
                )
            )
        ):
            return

        self._generation += 1
        gen = self._generation
        self._target_src = src
        self._cached_path = None
        self._status = "pending"
        self._error = None
        delay = max(0.0, _get_float("startDelaySec", 2.0))
        omni.log.warn(
            f"[{_EXT_ID}] Disk preload scheduled in {delay:.1f}s: "
            f"{os.path.basename(src)}"
        )
        self._task = asyncio.ensure_future(self._run(src, gen, delay))

    def cancel(self) -> None:
        self._generation += 1
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
        if self._status not in ("ready", "idle"):
            self._status = "cancelled"

    def shutdown(self) -> None:
        self.cancel()
        self._cleanup_session_files()
        self._target_src = None
        self._cached_path = None
        self._status = "idle"
        self._error = None

    async def _run(self, src: str, gen: int, delay: float) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            if gen != self._generation:
                return

            self._status = "disk"
            t0 = time.perf_counter()
            cache_dir = _get_str("localCacheDir", "/tmp/mos_usdz_cache").strip()

            if cache_dir:
                dest = await asyncio.to_thread(
                    self._copy_to_cache_sync, src, cache_dir, gen
                )
                if gen != self._generation:
                    return
                if dest is None:
                    self._status = "failed"
                    self._error = "copy_failed"
                    return
                self._cached_path = dest
                self._session_files.add(dest)
                self._prune_cache(cache_dir)
            else:
                ok = await asyncio.to_thread(self._warm_page_cache_sync, src, gen)
                if gen != self._generation:
                    return
                if not ok:
                    self._status = "failed"
                    self._error = "warm_failed"
                    return
                self._cached_path = None

            if gen != self._generation:
                return
            elapsed = time.perf_counter() - t0
            self._status = "ready"
            size_mb = os.path.getsize(src) / (1024 * 1024)
            omni.log.warn(
                f"[{_EXT_ID}] Disk preload ready: {os.path.basename(src)} "
                f"({size_mb:.0f} MiB in {elapsed:.1f}s"
                f"{', cached' if self._cached_path else ', page-cache'})"
            )
        except asyncio.CancelledError:
            if gen == self._generation:
                self._status = "cancelled"
            raise
        except Exception as exc:
            if gen == self._generation:
                self._status = "failed"
                self._error = str(exc)
                omni.log.warn(f"[{_EXT_ID}] Disk preload failed: {exc}")

    def _copy_to_cache_sync(self, src: str, cache_dir: str, gen: int) -> Optional[str]:
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except OSError as exc:
            omni.log.warn(f"[{_EXT_ID}] Cannot create cache dir {cache_dir}: {exc}")
            return None

        dest = os.path.join(cache_dir, _cache_filename(src))
        try:
            src_size = os.path.getsize(src)
            if os.path.isfile(dest) and os.path.getsize(dest) == src_size:
                return dest
        except OSError:
            pass

        tmp = dest + ".partial"
        try:
            with open(src, "rb") as rf, open(tmp, "wb") as wf:
                chunks = 0
                while True:
                    if gen != self._generation:
                        break
                    buf = rf.read(_CHUNK_BYTES)
                    if not buf:
                        break
                    wf.write(buf)
                    chunks += 1
                    if chunks % _YIELD_EVERY_CHUNKS == 0:
                        time.sleep(0.002)
            if gen != self._generation:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                return None
            os.replace(tmp, dest)
            return dest
        except Exception as exc:
            omni.log.warn(f"[{_EXT_ID}] Cache copy failed for {src}: {exc}")
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            return None

    def _warm_page_cache_sync(self, src: str, gen: int) -> bool:
        try:
            with open(src, "rb") as rf:
                chunks = 0
                while True:
                    if gen != self._generation:
                        return False
                    buf = rf.read(_CHUNK_BYTES)
                    if not buf:
                        break
                    chunks += 1
                    if chunks % _YIELD_EVERY_CHUNKS == 0:
                        time.sleep(0.002)
            return True
        except Exception as exc:
            omni.log.warn(f"[{_EXT_ID}] Page-cache warm failed for {src}: {exc}")
            return False

    def _prune_cache(self, cache_dir: str) -> None:
        keep = set()
        if self._cached_path:
            keep.add(self._cached_path)
        if self._pinned_open_path:
            keep.add(self._pinned_open_path)
        for path in list(self._session_files):
            if path in keep:
                continue
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
            self._session_files.discard(path)
        try:
            for name in os.listdir(cache_dir):
                if name.endswith(".partial"):
                    try:
                        os.remove(os.path.join(cache_dir, name))
                    except OSError:
                        pass
        except OSError:
            pass

    def _cleanup_session_files(self) -> None:
        for path in list(self._session_files):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
        self._session_files.clear()
        self._pinned_open_path = None
        cache_dir = _get_str("localCacheDir", "/tmp/mos_usdz_cache").strip()
        if cache_dir and self._target_src:
            partial = os.path.join(
                cache_dir, _cache_filename(self._target_src) + ".partial"
            )
            try:
                if os.path.isfile(partial):
                    os.remove(partial)
            except OSError:
                pass


# ── Phase C: GPU-resident dual slots ───────────────────────────────────────────

class DualSlotController:
    """Compose two USDZ references under one stage; swap visibility on Next."""

    def __init__(self, disk: DiskPreloader) -> None:
        self._disk = disk
        self._task: Optional[asyncio.Task] = None
        self._generation: int = 0
        self._active_key: str = "A"
        self._paths: dict[str, Optional[str]] = {"A": None, "B": None}
        self._standby_status: str = "idle"  # idle|loading|ready|failed
        self._bootstrapped: bool = False
        # Optional: (slot_prim_path) -> None, set by extension for orientation.
        self.orient_slot = None

    @property
    def enabled(self) -> bool:
        return gpu_resident_enabled()

    @property
    def bootstrapped(self) -> bool:
        return self._bootstrapped

    def active_slot_path(self) -> str:
        return _SLOT_A if self._active_key == "A" else _SLOT_B

    def standby_slot_path(self) -> str:
        return _SLOT_B if self._active_key == "A" else _SLOT_A

    def standby_ready_for(self, src_path: str) -> bool:
        other = "B" if self._active_key == "A" else "A"
        return (
            self._standby_status == "ready"
            and self._paths.get(other) == _norm(src_path)
        )

    def cancel(self) -> None:
        self._generation += 1
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
        if self._standby_status == "loading":
            self._standby_status = "idle"

    def shutdown(self) -> None:
        self.cancel()
        self._paths = {"A": None, "B": None}
        self._standby_status = "idle"
        self._bootstrapped = False
        self._active_key = "A"

    async def bootstrap_active(self, src_path: str) -> Tuple[bool, str]:
        """Create wrapper stage and load *src_path* into slot A (visible)."""
        self.cancel()
        t0 = time.perf_counter()
        open_path = self._disk.resolve_open_path(src_path)
        self._disk.pin_open_path(open_path)

        ctx = omni.usd.get_context()
        try:
            if hasattr(ctx, "new_stage_async"):
                ok, err = await ctx.new_stage_async()
                if not ok:
                    return False, err or "new_stage_async failed"
            else:
                ctx.new_stage()
        except Exception as exc:
            return False, str(exc)

        if not self._ensure_slots():
            return False, "failed to create MosSlot prims"

        self._active_key = "A"
        self._paths = {"A": _norm(src_path), "B": None}
        self._standby_status = "idle"
        self._bootstrapped = True

        if not self._set_slot_reference("A", open_path, visible=True):
            return False, "failed to reference active USDZ"
        self._set_slot_parked("A", parked=False)
        self._set_slot_visible("B", False)

        await self._wait_stage_loaded(timeout_s=300.0)
        if callable(self.orient_slot):
            try:
                self.orient_slot(_SLOT_A)
            except Exception:
                pass
        elapsed = time.perf_counter() - t0
        omni.log.warn(
            f"[{_EXT_ID}] Dual-slot bootstrap {os.path.basename(src_path)} "
            f"in {elapsed:.1f}s (open={open_path})"
        )
        return True, ""

    async def load_into_active(self, src_path: str) -> Tuple[bool, str]:
        """Load *src_path* into the current active slot (blocking). Used as fallback."""
        if not self._bootstrapped:
            return await self.bootstrap_active(src_path)

        t0 = time.perf_counter()
        open_path = self._disk.resolve_open_path(src_path)
        self._disk.pin_open_path(open_path)
        key = self._active_key
        if not self._set_slot_reference(key, open_path, visible=True):
            return False, "failed to reference USDZ into active slot"
        self._paths[key] = _norm(src_path)
        self._set_slot_parked(key, parked=False)
        other = "B" if key == "A" else "A"
        self._clear_slot_reference(other)
        self._paths[other] = None
        self._set_slot_visible(other, False)
        self._standby_status = "idle"
        await self._wait_stage_loaded(timeout_s=300.0)
        if callable(self.orient_slot):
            try:
                self.orient_slot(self.active_slot_path())
            except Exception:
                pass
        elapsed = time.perf_counter() - t0
        omni.log.warn(
            f"[{_EXT_ID}] Dual-slot active load {os.path.basename(src_path)} "
            f"in {elapsed:.1f}s"
        )
        return True, ""

    def schedule_standby(self, src_path: Optional[str]) -> None:
        """Background: disk-prefetch then compose *src_path* into the standby slot."""
        self.cancel()
        if not src_path or not self.enabled or not self._bootstrapped:
            return
        if _get_int("lookahead", 1) < 1:
            return

        src = _norm(src_path)
        other = "B" if self._active_key == "A" else "A"
        if self._standby_status == "ready" and self._paths.get(other) == src:
            return

        self._generation += 1
        gen = self._generation
        self._standby_status = "loading"
        delay = max(0.0, _get_float("startDelaySec", 2.0))
        omni.log.warn(
            f"[{_EXT_ID}] GPU standby scheduled in {delay:.1f}s: "
            f"{os.path.basename(src)}"
        )
        self._task = asyncio.ensure_future(self._standby_run(src, gen, delay))

    def activate_standby(self, src_path: str) -> bool:
        """Instant path: swap visibility if standby matches *src_path*."""
        src = _norm(src_path)
        if not self.standby_ready_for(src):
            return False

        t0 = time.perf_counter()
        old = self._active_key
        new = "B" if old == "A" else "A"

        # Bring standby on-camera, park/hide the old active, then drop its ref.
        self._set_slot_parked(new, parked=False)
        self._set_slot_visible(new, True)
        self._set_slot_visible(old, False)
        self._clear_slot_reference(old)
        self._paths[old] = None
        self._active_key = new
        self._standby_status = "idle"

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        omni.log.warn(
            f"[{_EXT_ID}] GPU standby ACTIVATE {os.path.basename(src)} "
            f"in {elapsed_ms:.1f} ms (slot {new})"
        )
        return True

    async def _standby_run(self, src: str, gen: int, delay: float) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            if gen != self._generation:
                return

            # Prefer local cache; kick disk job if not ready yet.
            if self._disk.status_for(src) != "ready":
                self._disk.schedule(src)
                # Wait for disk ready (or timeout) before composing.
                disk_wait_t0 = time.perf_counter()
                while self._disk.status_for(src) not in ("ready", "failed", "idle"):
                    if gen != self._generation:
                        return
                    if time.perf_counter() - disk_wait_t0 > 180.0:
                        break
                    await asyncio.sleep(0.25)

            if gen != self._generation:
                return

            open_path = self._disk.resolve_open_path(src)
            other = "B" if self._active_key == "A" else "A"
            slot_path = _SLOT_A if other == "A" else _SLOT_B
            t0 = time.perf_counter()
            omni.log.warn(
                f"[{_EXT_ID}] GPU standby composing {os.path.basename(src)} "
                f"from {open_path}"
            )
            # Visible but parked far away so RTX/Hydra still upload Gaussians
            # without occluding the participant's view of the active scene.
            if not self._set_slot_reference(other, open_path, visible=True):
                self._standby_status = "failed"
                return
            self._set_slot_parked(other, parked=True)
            self._paths[other] = src
            if callable(self.orient_slot):
                try:
                    self.orient_slot(slot_path)
                except Exception:
                    pass
            # Re-apply park after orientation (orient may reset xform ops).
            self._set_slot_parked(other, parked=True)

            await self._wait_stage_loaded(timeout_s=300.0)
            if gen != self._generation:
                return

            # Extra frames so the renderer can finish GPU upload.
            app = omni.kit.app.get_app()
            for _ in range(30):
                if gen != self._generation:
                    return
                await app.next_update_async()

            self._standby_status = "ready"
            elapsed = time.perf_counter() - t0
            omni.log.warn(
                f"[{_EXT_ID}] GPU standby READY {os.path.basename(src)} "
                f"in {elapsed:.1f}s (slot {other}, parked off-camera)"
            )
        except asyncio.CancelledError:
            if gen == self._generation:
                self._standby_status = "idle"
            raise
        except Exception as exc:
            if gen == self._generation:
                self._standby_status = "failed"
                omni.log.warn(f"[{_EXT_ID}] GPU standby failed: {exc}")

    def _ensure_slots(self) -> bool:
        try:
            from pxr import Sdf, Usd, UsdGeom

            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return False
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                world = stage.GetPrimAtPath("/World")
                if not world or not world.IsValid():
                    world = stage.DefinePrim("/World", "Xform")
                for path in (_SLOT_A, _SLOT_B):
                    prim = stage.GetPrimAtPath(path)
                    if not prim or not prim.IsValid():
                        prim = stage.DefinePrim(Sdf.Path(path), "Xform")
                    UsdGeom.Xformable(prim)
            return True
        except Exception as exc:
            omni.log.warn(f"[{_EXT_ID}] _ensure_slots failed: {exc}")
            return False

    def _set_slot_reference(self, key: str, asset_path: str, visible: bool) -> bool:
        try:
            from pxr import Sdf, Usd, UsdGeom

            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return False
            prim_path = _SLOT_A if key == "A" else _SLOT_B
            session = stage.GetSessionLayer()
            abs_asset = os.path.abspath(asset_path)
            with Usd.EditContext(stage, session):
                prim = stage.GetPrimAtPath(prim_path)
                if not prim or not prim.IsValid():
                    prim = stage.DefinePrim(Sdf.Path(prim_path), "Xform")
                refs = prim.GetReferences()
                refs.ClearReferences()
                refs.AddReference(Sdf.Reference(abs_asset))
                img = UsdGeom.Imageable(prim)
                if visible:
                    img.MakeVisible()
                else:
                    img.MakeInvisible()
            return True
        except Exception as exc:
            omni.log.warn(f"[{_EXT_ID}] _set_slot_reference({key}) failed: {exc}")
            return False

    def _clear_slot_reference(self, key: str) -> None:
        try:
            from pxr import Usd

            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return
            prim_path = _SLOT_A if key == "A" else _SLOT_B
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                prim = stage.GetPrimAtPath(prim_path)
                if prim and prim.IsValid():
                    prim.GetReferences().ClearReferences()
        except Exception as exc:
            omni.log.warn(f"[{_EXT_ID}] _clear_slot_reference({key}) failed: {exc}")

    def _set_slot_visible(self, key: str, visible: bool) -> None:
        try:
            from pxr import Usd, UsdGeom

            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return
            prim_path = _SLOT_A if key == "A" else _SLOT_B
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                prim = stage.GetPrimAtPath(prim_path)
                if not prim or not prim.IsValid():
                    return
                img = UsdGeom.Imageable(prim)
                if visible:
                    img.MakeVisible()
                else:
                    img.MakeInvisible()
        except Exception as exc:
            omni.log.warn(f"[{_EXT_ID}] _set_slot_visible({key}) failed: {exc}")

    def _set_slot_parked(self, key: str, parked: bool) -> None:
        """Translate slot far from origin while warming so it stays off-camera."""
        try:
            from pxr import Gf, Usd, UsdGeom

            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return
            prim_path = _SLOT_A if key == "A" else _SLOT_B
            session = stage.GetSessionLayer()
            with Usd.EditContext(stage, session):
                prim = stage.GetPrimAtPath(prim_path)
                if not prim or not prim.IsValid():
                    return
                xf = UsdGeom.Xformable(prim)
                # Preserve rotation from orientation; set translate separately.
                translate = Gf.Vec3d(0.0, 0.0, -1.0e6 if parked else 0.0)
                # Find or add a translate op after any transform/rotate ops.
                ops = xf.GetOrderedXformOps()
                t_op = None
                for op in ops:
                    try:
                        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                            t_op = op
                            break
                    except Exception:
                        continue
                if t_op is None:
                    t_op = xf.AddTranslateOp(opSuffix="mos_park")
                t_op.Set(translate)
        except Exception as exc:
            omni.log.warn(f"[{_EXT_ID}] _set_slot_parked({key}) failed: {exc}")

    async def _wait_stage_loaded(self, timeout_s: float = 120.0) -> None:
        """Wait until Kit reports stage loading idle (best-effort)."""
        app = omni.kit.app.get_app()
        ctx = omni.usd.get_context()
        t0 = time.perf_counter()
        # A few frames for the reference to register.
        for _ in range(3):
            await app.next_update_async()

        stable = 0
        while time.perf_counter() - t0 < timeout_s:
            await app.next_update_async()
            loading = False
            try:
                # Returns (activity, loaded, total) on many Kit builds.
                status = ctx.get_stage_loading_status()
                if isinstance(status, tuple) and len(status) >= 3:
                    _activity, loaded, total = status[0], status[1], status[2]
                    if total and loaded < total:
                        loading = True
                elif isinstance(status, tuple) and len(status) == 2:
                    loaded, total = status
                    if total and loaded < total:
                        loading = True
            except Exception:
                pass
            try:
                if hasattr(ctx, "is_stage_loading") and ctx.is_stage_loading():
                    loading = True
            except Exception:
                pass

            if not loading:
                stable += 1
                if stable >= 5:
                    return
            else:
                stable = 0
