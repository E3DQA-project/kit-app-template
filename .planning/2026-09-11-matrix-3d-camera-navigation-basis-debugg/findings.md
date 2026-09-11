# Findings & Decisions

## Requirements
- Initial Matrix-3D view must remain correct.
- Pan input must not manifest as roll.
- Both active viewers must use the same method-specific camera logic.
- Do not commit the correction until it is verified in the GUI session.

## Research Findings
- `recover_p4_cameras.py` treats the source camera rotation as camera-to-world in column-vector form.
- The Matrix-3D exporter converts camera poses with `pose @ diag(1,-1,-1)` and then calls `column_vector_4x4_to_usd_matrix`, which transposes the 3x3 rotation for USD.
- Both active viewers currently construct `Gf.Matrix4d` by writing the JSON rotation rows directly, while putting translation in the bottom row. This is wrong for non-axis-aligned poses.
- Axis-aligned camera 0 matrices are symmetric/diagonal, hiding the transpose error and explaining why facing can appear correct.
- The corrective 180-degree roll must be composed on the camera-to-world pose before the USD-boundary transpose.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Test a matrix-boundary transpose before changing navigation settings | The symptom is shared by both viewers and originates in the imported pose basis; changing Kit controls would mask the source error. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-
