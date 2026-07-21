# MOS App — Asynchronous Scene Preload Feasibility Report

**App:** `nycu.mos_app.kit`  
**Extension:** `nycu.mos_app_extension`  
**Date:** 2026-07-16  
**Status:** Phase A verified ineffective for wall-clock; Phase C dual-slot implemented  
**Hardware context:** NVIDIA GeForce RTX 5090 (≈32 GB VRAM), shared lab machine  

### Pilot finding (2026-07-16)

Phase A **did run** (local cache under `/tmp/mos_usdz_cache` filled with next USDZs on `/dev/sda2`), but **Next was still ~20 s**. Conclusion: the gap is dominated by **USD compose + 3DGS GPU upload**, not NAS I/O. Disk prefetch alone cannot fix MOS pacing.

### Current implementation (Phase A + Phase C)

| Item | Location |
|---|---|
| Disk + dual-slot controller | `…/nycu/mos_app_extension/scene_preload.py` |
| Load / swap hooks | `extension.py` → `_load_scene_async`, `_schedule_next_preload` |
| Default mode | `preload.mode = "gpu_resident"` in `.kit` / `extension.toml` |

**GPU-resident behavior:** scenes are composed into `/World/MosSlotA|B` on one wrapper stage. While navigating N, N+1 is referenced into the standby slot, parked far off-camera (so RTX still uploads), then on **Next** visibility/park is swapped and the old slot’s reference is cleared. Watch logs for `GPU standby READY` then `Transition (GPU swap) … ms`.

Fallback: if standby is not ready, loads into the active slot (still dual-slot) or legacy `open_stage`.

---

## 1. Executive summary

The MOS evaluation loop currently blocks for roughly **~20 seconds** between scenes because each **Next** action unloads the active USDZ stage and opens the next one on the default `UsdContext`. That gap is long enough to affect participant mood and subjective-task performance.

**Verdict:** Asynchronous / background loading **is feasible** and worthwhile for MOS, but:

1. Kit’s `open_stage_async` on the **same** context is **not** background preload — it still replaces the visible stage.
2. True zero-wait transitions require the next scene to be **already resident** (at least partially) while the participant explores the current scene.
3. With exclusive GPU access negotiated on the 5090, dual residency becomes a realistic stretch goal; without headroom measurement, start with a safer **lookahead = 1** pipeline (disk + USD warmup first, GPU-ready second).

**Recommended strategy:** implement in **three phases** inside `nycu.mos_app_extension` (no changes to setup/messaging extensions), gated by measured VRAM and frame-time impact during navigation.

---

## 2. Problem statement

### 2.1 Experiment impact

MOS is a sequential subjective evaluation workflow:

```
Navigate scene N → score → Next → (long load) → Navigate scene N+1 → …
```

A consistent ~20 s blackout / spinner between stimuli:

- Breaks immersion and pacing
- Introduces irritation / fatigue confounders
- Makes session length harder to control
- Risks unequal effective viewing conditions if load time varies by file size

### 2.2 Asset characteristics

Scenes in `source/data/mos_scenes.json` are large 3DGS USDZ packages under NAS, e.g.:

| Example asset | On-disk size |
|---|---|
| `generated_3dgs_opt_downsample_p0.25.usdz` | ~298 MB |
| `generated_3dgs_opt.usdz` (full) | ~1.2 GB |
| Typical degraded variants in the same folder | ~0.5–1.2 GB |

Load time is dominated by a mix of:

1. **NAS / disk I/O** (read + decompress USDZ)
2. **USD stage open / composition**
3. **RTX / 3DGS GPU upload and first-frame settle**

Any preload design must attack these layers separately; hiding only one layer will not eliminate the full ~20 s.

### 2.3 Observed VRAM context

On the shared 5090, occupancy around **~20 GB** has been observed while classmates also use the machine. For dual-resident preload experiments, **scheduled exclusive use** is assumed so peak VRAM can be attributed to MOS alone.

---

## 3. Current architecture (baseline)

### 3.1 Ownership

| Component | Role in loading |
|---|---|
| `nycu.mos_app.kit` | App shell; sets `sceneListPath` |
| `nycu.mos_app_extension` | Scene list, unload/open, camera init, scoring, Next |
| `nycu.my_usd_viewer_setup_extension` | Viewport layout only (do not modify) |
| `nycu.my_usd_viewer_messaging_extension` | Streaming messaging (idle locally; do not modify) |

### 3.2 Current load path

In `extension.py`:

1. Resolve ordered `.usdz` list from JSON.
2. On start / Next: `_load_scene()`.
3. `_unload_stage()` → `close_stage()` + empty `new_stage()` (+ GC).
4. `omni.usd.get_context().open_stage(path)` on the **default** context.
5. Wait for `StageEventType.OPENED`.
6. `_post_load()`: orientation fix, `cameras.json` pose, capture reset transform, return to `NAVIGATING`.

This matches PRD **FR-2.6** (explicit unload to release VRAM) and **FR-2.7** (`open_stage` / async equivalent).

### 3.3 Why the gap is structural

```
[Scene N rendered] --Next--> [unload] --[open N+1]--[GPU settle]--> [Scene N+1 rendered]
                              \_____________ ~20 s gap _____________/
```

There is **no lookahead**. Work for scene `N+1` begins only after the participant submits scores.

---

## 4. What “async” means in Kit (and what it does not)

### 4.1 `open_stage_async` (already in the template)

`nycu.my_usd_viewer_setup_extension` uses:

```python
await usd_context.open_stage_async(url, omni.usd.UsdContextInitialLoadSet.LOAD_ALL)
```

This avoids blocking the Python main thread during open, but:

- Still targets a **single** context (usually the default one bound to the viewport)
- Still **replaces** the current stage
- Does **not** keep scene N interactive while scene N+1 loads into that same context

**Conclusion:** Switching MOS from `open_stage` → `open_stage_async` improves UI responsiveness during load, but **does not** solve the inter-stimulus blank period by itself.

### 4.2 Multiple `UsdContext` instances (Kit-supported)

Omniverse Kit’s `omni.usd` supports named contexts:

```python
preload_ctx = omni.usd.create_context("mos_preload")
await preload_ctx.open_stage_async(next_url, omni.usd.UsdContextInitialLoadSet.LOAD_ALL)
```

Key properties:

- Default context (`omni.usd.get_context()`) remains the viewport source.
- Secondary contexts can hold another stage without changing what the participant sees.
- Hydra engines may be attached per context; **avoid attaching a second RTX viewport** during trials unless dual GPU residency is intentional.

### 4.3 Same-stage dual references / payloads

An alternative is one stage with two prim trees (or payloads), toggling visibility / load rules:

```
/World/Active   → scene N   (visible, rendered)
/World/Standby  → scene N+1 (loaded, invisible or deactivated)
```

On Next: swap Active/Standby, unload previous Active, start prefetching N+2 into Standby.

This can yield the fastest visual switch, but couples both scenes’ GPU cost into one Hydra world and needs careful unload to avoid VRAM leaks.

---

## 5. Goals and non-goals

### 5.1 Goals

| ID | Goal |
|---|---|
| G1 | Keep scene N fully interactive (fly/nav + scoring) while preparing scene N+1 |
| G2 | Reduce median Next→ready time toward **near-instant** when preload completes in time |
| G3 | Avoid FPS hitches that confound navigation quality during the trial |
| G4 | Fail soft: if preload is incomplete, fall back to today’s unload/open path |
| G5 | Confine changes to `nycu.mos_app_extension` (+ kit settings / report docs) |

### 5.2 Non-goals (v1)

| ID | Out of scope |
|---|---|
| NG1 | Prefetching the entire session list into VRAM |
| NG2 | Changing scoring schema or experiment protocol semantics |
| NG3 | Multi-user concurrent MOS in one process |
| NG4 | Guaranteeing zero wait for every transition regardless of participant speed |

---

## 6. Recommended approach (phased)

Implement **lookahead = 1** (only the next scene). Deeper queues burn VRAM and increase hitch risk with little MOS benefit.

### Phase A — Disk / OS cache prefetch (low risk, high ROI for NAS)

**Idea:** As soon as scene N enters `NAVIGATING`, start reading `scenes[N+1]` in a background asyncio/thread task (sequential read into a discard buffer, or `cp`/`os.sendfile` to local NVMe cache).

**What it hides:** NAS latency and cold page-cache misses.  
**What it does not hide:** GPU upload after `open_stage`.

**Implementation sketch:**

```python
async def _prefetch_file(path: str) -> None:
    # Prefer local SSD staging dir if NAS path detected
    # else sequential read to warm page cache
    ...
```

**Settings (proposed):**

```toml
[settings.exts."nycu.mos_app_extension"]
preload.enabled = true
preload.mode = "disk"          # disk | usd_context | gpu_resident
preload.lookahead = 1
preload.localCacheDir = "/tmp/mos_usdz_cache"   # optional NVMe
```

**Success metric:** Reduce open time for NAS-hosted 1.2 GB USDZ when participant spends ≥20–30 s navigating.

---

### Phase B — Secondary `UsdContext` USD warmup (medium risk, medium–high ROI)

**Idea:** After disk prefetch (or in parallel), open the next USDZ on a named context **without** a visible Hydra viewport:

```python
CTX_PRELOAD = "mos_preload"

def _ensure_preload_context():
    ctx = omni.usd.get_context(CTX_PRELOAD)
    if ctx is None:
        ctx = omni.usd.create_context(CTX_PRELOAD)
    return ctx

async def _warmup_next_stage(url: str):
    ctx = _ensure_preload_context()
    # Do not attach extra Hydra engines here for Phase B
    ok, err = await ctx.open_stage_async(
        url, omni.usd.UsdContextInitialLoadSet.LOAD_ALL
    )
    ...
```

**On Next (fast path):**

1. If preload context holds the expected URL and is ready:
   - Option B1 (simpler): `default.open_stage_async(url)` — still re-opens, but benefits from OS/USD caches warmed by secondary open.
   - Option B2 (stronger, more work): transfer/attach warmed stage into the default context if Kit APIs allow (`attach_stage_async`), then destroy/recreate preload stage for N+2.
2. Else: fall back to current unload + open path.
3. Always run existing `_post_load()` (orientation, cameras.json, reset capture).

**Important:** Empirically verify whether a secondary-context open without Hydra already pulls large Gaussian buffers into VRAM. If it does, Phase B collapses into Phase C for memory planning.

**Success metric:** Meaningful reduction of USD open wall time without >5% sustained FPS drop during navigation.

---

### Phase C — GPU-resident standby (high reward, VRAM-gated)

Only after exclusive GPU time and measurement.

**Option C1 — Dual reference / payload swap (preferred if stable)**

1. Build a thin wrapper stage (or session-layer composition) that references scene N and scene N+1.
2. Render only Active; keep Standby loaded but invisible / non-picked.
3. On Next: atomic visibility swap + camera re-init; asynchronously unload old Active and load N+2 into Standby.

**Option C2 — Dual context + Hydra, swap viewport binding**

1. Default context renders scene N.
2. Preload context opens N+1 and attaches an RTX Hydra engine **off-screen** or to a hidden viewport.
3. On Next: retarget the visible viewport to the preload context (or swap context roles), then recycle the old context.

C2 is more aligned with Kit’s multi-context model but needs careful viewport/utility API work in a USD Viewer (non-editor) app.

**VRAM rule of thumb:**

```
peak(scene) × 2 + app overhead  <  32 GB × safety_margin(0.85)
```

If measured peak for a full 1.2 GB 3DGS scene is ~14–16 GB, dual residency is plausible. If peak is ~18–22 GB, Phase C is not viable for full assets (still viable for downsampled variants).

**Success metric:** Next→interactive P95 < 1 s when preload ready; navigation FPS during preload within experiment tolerance (define before pilots).

---

## 7. Proposed runtime state machine

Extend the existing MOS states (`LOADING`, `NAVIGATING`, scoring, etc.) with preload substates:

```
                    ┌──────────────────────────────┐
                    │         NAVIGATING           │
                    │  (scene N interactive)       │
                    │                              │
                    │  background:                 │
                    │   PREFETCH_DISK → WARM_USD   │
                    │   → (optional) GPU_READY     │
                    └──────────────┬───────────────┘
                                   │ Next / submit
                                   ▼
                    ┌──────────────────────────────┐
                    │        TRANSITION            │
                    │  if GPU_READY / WARM_USD:    │
                    │      fast activate + post    │
                    │  else:                       │
                    │      unload + open (legacy)  │
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │     NAVIGATING (N+1)         │
                    │  kick preload for N+2        │
                    └──────────────────────────────┘
```

**UI/status suggestions (non-intrusive):**

- Silent by default (do not show “Loading next…” during the trial — avoids expectancy bias).
- Optional debug HUD via setting `preload.showStatus = true` for engineering pilots only.
- If Next pressed early: show the existing loading status; do not block score save.

---

## 8. Concrete integration points in `nycu.mos_app_extension`

| Hook | Change |
|---|---|
| After `_post_load()` succeeds | Start `_schedule_preload(self._index + 1)` |
| On `_advance` / Next | Await/cancel-safe activate of preloaded target; else `_load_scene()` legacy |
| `_unload_stage()` | Keep for legacy path and for discarding the *previous* scene after a successful swap |
| Extension shutdown | Cancel preload tasks; `destroy_context("mos_preload")`; clear local cache files for this session |
| Settings | Add `preload.*` keys under `/exts/nycu.mos_app_extension/` in `.kit` / `extension.toml` |

### 8.1 Suggested module split (optional but clean)

Keep PRD-friendly structure without rewriting everything at once:

```
nycu/mos_app_extension/
  extension.py           # orchestration (existing)
  scene_preload.py       # NEW: disk/usd/gpu preload controller
```

`scene_preload.py` responsibilities:

- Resolve next path
- Deduplicate / cancel superseded jobs when index changes
- Expose `status_for(path) -> idle|disk|usd|gpu|ready|failed`
- Expose `activate(path) -> bool` for Transition

### 8.2 Concurrency rules

1. Only one preload job at a time.
2. Cancel or ignore results if `self._index` advanced past the job’s target.
3. Never call `open_stage` on the default context from the preload task.
4. Do not run heavy GPU warmup during the first few seconds after scene N appears (let FPS settle for the participant).

### 8.3 Interaction with PRD FR-2.6

FR-2.6 currently **requires** unload-before-open to free VRAM. Phase C intentionally relaxes this for the standby scene.

**Spec update needed before Phase C lands:**

- FR-2.6 becomes: “Unload scenes that are no longer Active or Standby; keep at most `preload.lookahead` non-active resident scenes.”
- Add NFR for preload hitch budget and fallback behavior.

Phases A/B can ship without changing FR-2.6 semantics for the *visible* stage.

---

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Secondary open still consumes large VRAM | OOM / driver reset mid-trial | Measure Phase B VRAM delta; auto-downgrade to disk-only |
| Background I/O hitches fly mode | Confounds navigation MOS | Throttle read rate; delay prefetch 2–3 s after settle; prefer local NVMe copy then idle |
| Dual Hydra engines unstable in USD Viewer template | Crash / black viewport | Prefer payload swap (C1) after prototype; keep legacy path |
| Participant presses Next before ready | Still sees a wait | Expected; show loading status; never drop scores |
| Local cache fills disk | Lab machine pain | Cap cache to lookahead files; delete on activate/shutdown |
| Shared GPU during pilots | Inflated VRAM / FPS noise | Exclusive scheduled sessions for measurement and formal MOS |
| Expectancy bias from “next is loading” UI | Validity threat | Keep preload invisible in formal runs |

---

## 10. Measurement plan (do this before / during Phase A pilots)

Run on exclusive 5090 time with a fixed scene pair (small + full):

| Metric | How |
|---|---|
| Peak VRAM scene N | `nvidia-smi` dmon / NVML after 10 s settle |
| Peak VRAM with N + preload(N+1) | Same, under each phase |
| Wall time: Next → `OPENED` | Extension timestamps |
| Wall time: `OPENED` → first stable frame | Timestamp after `_post_load` + N frames |
| Nav FPS p50/p95 during preload | Viewport / app FPS sampler |
| Split: disk vs open vs GPU | Disable phases selectively |

**Go / no-go for Phase C:**

- `2 * peak_vram(full_scene) + 2 GB < 0.85 * 32 GB`, **and**
- FPS p95 drop during GPU warmup within pre-agreed tolerance (suggest ≤10% relative for pilot; tighten for formal study).

---

## 11. Experiment protocol notes

Background loading is an engineering optimization; keep the **psychophysical protocol** constant:

1. Do not reveal preload status to participants in formal sessions.
2. Keep minimum free-viewing time rules unchanged (if any).
3. Log per-transition: `{scene_path, preload_mode, preload_ready, transition_ms, fallback_used}` into the score sidecar or a separate session log for later exclusion analysis.
4. If a transition falls back or hitches severely, flag that trial in logs (do not silently mix clean and disrupted trials in analysis without a covariate).

---

## 12. Implementation roadmap

| Step | Deliverable | Effort (eng.) | Depends on |
|---|---|---|---|
| 0 | Instrument timing + VRAM logging around `_load_scene` / `_post_load` | S | — |
| 1 | Phase A disk/local-cache prefetch + settings | S–M | Step 0 |
| 2 | Phase B secondary `UsdContext` warmup + fallback activate | M | Step 1 + VRAM check |
| 3 | Spec update (FR-2.6 / NFR preload) | S | Decision on Phase C |
| 4 | Phase C GPU-resident swap prototype (C1 or C2) | L | Exclusive GPU + go/no-go |
| 5 | Pilot MOS sessions; tune delay/throttle; freeze mode for study | M | Step 2 or 4 |

**Suggested default for first engineering PR:** Steps 0–1 (instrumentation + disk prefetch), with Phase B behind `preload.mode = "usd_context"`.

---

## 13. Configuration sketch (target)

```toml
# nycu.mos_app.kit (or extension defaults)
[settings.exts."nycu.mos_app_extension"]
sceneListPath = "${app}/../data/mos_scenes.json"

preload.enabled = true
preload.mode = "disk"                 # disk | usd_context | gpu_resident
preload.lookahead = 1
preload.startDelaySec = 2.0           # after NAVIGATING settle
preload.localCacheDir = "/tmp/mos_usdz_cache"
preload.showStatus = false            # true only for engineering
preload.fpsGuard = true               # pause/throttle if FPS collapses
```

---

## 14. Conclusion

Background loading for MOS is **feasible on this stack** and well-motivated for subjective experiments. Kit already provides the necessary primitives (`open_stage_async`, named `UsdContext`s, stage attach APIs), and the MOS extension already owns the scene index lifecycle — so the feature belongs in `nycu.mos_app_extension`.

The correct design is **not** “make `open_stage` async.” It is a **lookahead pipeline**:

1. Warm the next USDZ on disk while the user explores,
2. Optionally parse it on a secondary context,
3. Optionally keep it GPU-ready when exclusive 32 GB headroom is proven,

with **hard fallback** to today’s unload/open path whenever preload is late or unsafe.

With classmates off the machine for scheduled runs, Phase C is worth prototyping; until VRAM peaks are measured, ship Phase A/B to recover most of the NAS-bound portion of the ~20 s gap without risking OOM mid-trial.

---

## Appendix A — Key code references

| Item | Path |
|---|---|
| Current unload + open | `source/extensions/nycu.mos_app_extension/nycu/mos_app_extension/extension.py` (`_unload_stage`, `_load_scene`, `_on_stage_event`, `_post_load`) |
| Existing async open example | `source/extensions/nycu.my_usd_viewer_setup_extension/nycu/my_usd_viewer_setup_extension/setup.py` |
| PRD load requirements | `source/apps/nycu.mos_app_PRD.md` (§ FR-2, NFR-2) |
| Scene list | `source/data/mos_scenes.json` |
| App wiring | `source/apps/nycu.mos_app.kit` |

## Appendix B — Related Kit APIs (reference)

- `omni.usd.get_context()` / `omni.usd.create_context(name)` / `omni.usd.destroy_context(name)`
- `UsdContext.open_stage_async(url, load_set=LOAD_ALL)`
- `UsdContext.attach_stage_async(stage)` (evaluate for Phase B2 / C)
- `UsdContext.close_stage()` / `new_stage_async()`
- Stage event stream: `OPENED`, `OPEN_FAILED`, closing events

Exact attach/swap semantics should be validated against the Kit **110.0.0** build used by this template before committing to Phase C option C2.
