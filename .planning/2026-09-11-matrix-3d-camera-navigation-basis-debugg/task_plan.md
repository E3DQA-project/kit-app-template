# Task Plan: Matrix-3D camera navigation basis debugging

## Goal
Make Matrix-3D camera poses produce the correct initial view and correct Kit navigation axes in both active viewers.

## Next Step
Apply and verify the USD matrix-boundary transpose correction.

## Current Phase
Phase 2

## Phases

### Phase 1: Requirements & Discovery
- [x] Confirm initial view is correct but pan input produces roll.
- [x] Trace camera JSON generation and USD matrix construction.
- [x] Identify the row/column convention mismatch.
- **Status:** complete

### Phase 2: Hypothesis & Minimal Test
- [x] Define the USD-boundary transpose hypothesis.
- [ ] Implement the smallest shared behavior change in both viewers.
- **Status:** in_progress

### Phase 3: Implementation
- [ ] Execute the plan
- [ ] Write to files before executing
- **Status:** pending

### Phase 4: Testing & Verification
- [ ] Verify requirements met
- [ ] Document test results
- **Status:** pending

### Phase 5: Delivery
- [ ] Review outputs
- [ ] Deliver to user
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Keep camera pose calculations in column-vector camera-to-world form | This matches the dataset recovery and exporter code. |
| Transpose only when constructing USD `Gf.Matrix4d` | USD stores the equivalent row-vector matrix with translation in the bottom row. |

## Errors Encountered
| Error | Resolution |
|-------|------------|
