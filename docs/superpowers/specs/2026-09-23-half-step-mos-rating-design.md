# Cross-Platform Half-Step MOS Rating Design

## Goal

Make `mos_app` and `E3DQA_video_platform` collect comparable MOS ratings from 1.0 through 5.0 in 0.5 increments, while showing exactly five semantic anchors: `Very poor`, `Poor`, `Average`, `Good`, and `Very good`.

## Scope and constraints

- Both interfaces must default each metric to `3.0` and accept only values in `{1.0, 1.5, …, 5.0}`.
- The five anchor labels are fixed above the rail at the equally spaced whole-score positions. There are no numerical tick labels or visual labels for half values.
- Each row displays the current selection as one decimal place, including whole values (`3.0`).
- The web slider must use native range controls with `step="0.5"`; keyboard arrow input consequently changes by 0.5.
- The Kit app must use a float-capable model/control and its controller input must change by 0.5.
- Both persistence layers must write numeric half values without truncation. Existing integer score JSON remains valid and means the equivalent `.0` score.
- No new score categories or migration rewriting existing participant files are introduced.

## Interface design

Each metric has a two-line layout:

```text
Texture fidelity                                      3.5
Very poor       Poor        Average        Good       Very good
─────────────────────────────────────────────────────
                         ●
```

The web dialog widens its score rail and uses a grid/stacked metric row so labels have adequate room. The Kit score dialog uses the same hierarchy: metric name and numeric value, then the full-width rail with the five labels above it. Neither presentation exposes intermediate tick marks.

## Data contract

Scores are JSON numbers with a half-point precision. The valid domain is a finite set: `1.0`, `1.5`, `2.0`, `2.5`, `3.0`, `3.5`, `4.0`, `4.5`, `5.0`.

The video platform API schema accepts floats. Its normalization rejects or normalizes non-numeric values as existing behavior dictates, clamps range to 1.0–5.0, and snaps accepted numeric values to the nearest 0.5 before persisting. MOS applies the same clamp-and-snap rule when collecting models. A legacy JSON integer is already within this domain and remains readable without a conversion job.

## Components

### E3DQA_video_platform

- `backend/main.py`: accept `Dict[str, float]` for submitted scores.
- `backend/scores.py`: centralize half-step normalization/persistence and preserve metadata and existing files.
- `frontend/mos.js`: create range controls with a half step, render five anchors once per row, display numeric values with `toFixed(1)`, and remove the old selected-word indicator.
- `frontend/mos.css`: lay out wider two-line score rows and evenly distribute anchors above the rail.
- Existing backend and frontend tests: cover half-score validation/persistence and DOM contract where the project’s test harness supports it.

### kit-app-template MOS extension

- `extension.py`: replace integer score model/slider/collection with float-capable half-step behavior, display a one-decimal current value, and render five labels above each rail.
- Extension unit tests: assert the source-level UI and persistence contract, including use of a float model/slider and 0.5 step.

## Error handling and compatibility

Server-side normalization remains authoritative even though the UI constrains input. Scores below or above the bounds are clamped; values between half-step positions are snapped to the nearest valid half. Invalid non-numeric metric values use the current fallback behavior. API responses and historical files retaining integers must not cause session loading or score filtering to fail.

## Testing and acceptance criteria

- A submitted `3.5` persists as numeric `3.5` in both applications.
- Whole scores persist as numeric values and show as one decimal in the UI.
- Both sliders enforce a 0.5 increment from 1.0 through 5.0.
- Every rating row contains exactly the five approved semantic anchors and no half-value labels/ticks.
- Existing integer-only participant score files still support completion filtering.
- Relevant backend/extension test suites and the Kit build pass.
