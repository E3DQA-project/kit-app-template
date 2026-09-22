# Why repair camera handedness in the MOS app?

## Question

Why is the fix made in the Kit app's scene-loading path instead of editing the
USDZ files or their source `cameras.json` files?

## Answer

A reflected camera pose and a mirrored scene are separate issues. Some samples
have a reflected camera pose in their adjacent `cameras.json`: its 3-by-3
rotation determinant is `-1`, while a real rotation must have determinant
`+1`. That pose can invert the initial view and navigation, so it is safe to
repair at the app boundary.

It does **not** prove that a scene is mirrored. The validated `index_0014`
case has the reflected camera pose but normal scene geometry. Conversely,
`index_0030`, `index_0088`, `index_0106`, and `index_0114` remain visually
mirrored after the camera repair, so their reflection is inside the NuRec
scene payload or its upstream reconstruction coordinates.

MOS is the consumer that turns this external pose into `/BrowserCamera`, so it
is the narrowest safe repair boundary. The app now:

- leaves proper poses (`determinant ~= +1`) unchanged;
- repairs only the known Matrix-3D reflection (`determinant ~= -1`) by flipping
  the camera-local X basis; and
- logs any other malformed matrix without guessing a correction.

This preserves the original dataset and lets the correction be removed later
if the upstream camera exporter is fixed. It is deliberately not a geometry
repair; correcting a mirrored NuRec payload requires a separate, verified
pipeline-level transform.
