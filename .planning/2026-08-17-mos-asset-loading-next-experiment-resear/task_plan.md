# Task Plan: MOS asset-loading next-experiment research

## Goal
Create a practical wiki guide for isolating the measured 20.9–27.8 s `USD_ASSETS_LOADING → USD_ASSETS_LOADED` bottleneck.

## Next Step
Research official Kit profiling/tracing activation and local app support, then turn the findings into an experiment guide.

## Current Phase
Phase 1

## Phases

### Phase 1: Requirements & Discovery
- [x] Identify the measured bottleneck and current instrumentation limits.
- [x] Verify locally available Kit profiling/tracing support and official activation steps.
- [x] Compare experiment designs for storage, asset type, CPU/GPU tracing, and cold/warm cache control.
- **Status:** completed

### Phase 2: Wiki Guide
- [x] Draft an actionable next-experiment guide in `docs/wiki/`.
- [x] Link it from the MOS timing references.
- **Status:** completed

### Phase 3: Verification & Delivery
- [x] Check links, terminology, and working-tree scope.
- [x] Summarize the recommended next experiment.
- **Status:** completed

## Decisions Made
| Decision | Rationale |
|---|---|
| Target `USD_ASSETS_LOADING → USD_ASSETS_LOADED` | Measured 20.9–27.8 s; streaming idle and viewer policy are short. |
| Treat NAS-vs-SSD and CPU/GPU tracing as separate controlled comparisons | Each test answers a different causal question. |
| Add the activity-profiler dependency only for the trace run | It is cached locally but not a MOS-app dependency; it adds scene-loading spans without changing normal timing runs. |

## Errors Encountered
| Error | Resolution |
|---|---|
| Direct execution of the planning initializer was denied | Re-ran the script through Bash; plan files were created. |
