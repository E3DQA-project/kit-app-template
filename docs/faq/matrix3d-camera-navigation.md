# Matrix-3D camera navigation

## Why can a rightward pan appear to move the scene left?

The current Matrix-3D navigation basis is Y-up for Kit interaction, with the
camera looking along -Z. Camera translation and viewport-image motion have
opposite signs: moving the camera right makes the viewed scene move left. This
is expected for camera motion, but it must not be confused with an inverted
controller axis.

For the active Matrix-3D viewers, horizontal look input is normalized through
Kit's shared `lookSpeed/0` setting. It is negative so mouse and DualShock
horizontal input follow the participant's expected direction; the camera pose
itself is not changed.
