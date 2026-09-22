# Why repair camera handedness in the MOS app?

## Question

Why is the fix made in the Kit app's scene-loading path instead of editing the
USDZ files or their source `cameras.json` files?

## Answer

The USDZ geometry is not the problem. The anomalous samples have a reflected
camera pose in their adjacent `cameras.json`: its 3-by-3 rotation determinant
is `-1`, while a real rotation must have determinant `+1`. The reflected pose
makes the scene look left-right mirrored and reverses navigation.

MOS is the consumer that turns this external pose into `/BrowserCamera`, so it
is the narrowest safe repair boundary. The app now:

- leaves proper poses (`determinant ~= +1`) unchanged;
- repairs only the known Matrix-3D reflection (`determinant ~= -1`) by flipping
  the camera-local X basis; and
- logs any other malformed matrix without guessing a correction.

This preserves the original dataset and lets the correction be removed later
if the upstream camera exporter is fixed.
