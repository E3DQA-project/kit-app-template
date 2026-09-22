# Camera pose reflection versus mirrored NuRec geometry

## Corrected observation

The initial camera and navigation are now normal after MOS repairs a
`cameras.json` rotation with determinant `-1`. That repair does not decide
whether the rendered scene itself is mirrored.

| Index | `cameras.json` determinant | Camera after app repair | Scene geometry observed by user |
| --- | ---: | --- | --- |
| `0014` | `-1` | normal | normal |
| `0030` | `-1` | normal | left-right mirrored |
| `0037` | `+1` | normal | normal |
| `0088` | `-1` | normal | left-right mirrored |
| `0100` | `+1` | normal | normal |
| `0106` | `-1` | normal | left-right mirrored |
| `0114` | `-1` | normal | left-right mirrored |

## What was checked

For all seven USDZ files, `default.usda` and `gauss.usda` have the same:

- `upAxis = "Z"`;
- identity `xformOp:transform`; and
- NuRec reference layout.

There is no outer USD transform such as `scale(-1, 1, 1)` to repair. The
payload headers also use the same NuRec format and expose no per-scene
handedness metadata.

## Diagnosis

The camera determinant is a valid classifier for the camera-pose defect, but
not for geometry mirroring. The remaining geometry issue must originate in
the PLY/camera relationship in the Matrix-3D/Pano-GS pipeline or earlier.
Original P4 PLY files are retained. The converter reads each PLY's `x/y/z`
coordinates directly, exports with `dataset=None`, and does not enable the
3DGRUT-to-USDZ coordinate transform. There is no per-index transform in that
conversion path that could create a left-right reflection.

The original `condition/cameras.npz` frame-zero determinants match the later
`cameras.json` grouping: `0014/0030/0088/0106/0114` are `-1`, while
`0037/0100` are `+1`. `0014` proves that this signal alone is insufficient to
classify a visually mirrored scene.

## Next evidence to collect

1. Render an original PLY from frame-zero `condition/cameras.npz`.
2. Compare that render with the retained `condition/firstframe_rgb.png`.
