# Does left-right mirroring matter for NR 3D scene quality assessment?

## Question

The dataset will evaluate generated and reconstructed 3D scenes using
no-reference (NR) subjective quality assessment. Does a left-right mirrored
scene invalidate the experiment, especially when methods differ?

## Short answer

It is not automatically a visible quality defect in NR assessment, but it is a
serious **cross-method comparability confound**. Do not mix mirrored outputs
from one method with correctly oriented outputs from another method as though
they differed only in reconstruction quality.

## Why

NR observers do not see a reference image, so a consistent mirror can preserve
many local quality signals: Gaussian artifacts, holes, floaters, texture blur,
lighting quality, and navigation smoothness. For variants of the *same* base
scene from the *same* method, their relative quality ranking may remain useful
when all variants share the same orientation.

However, a mirror is not a neutral coordinate relabeling to a human observer.
Asymmetric objects, readable text, handed tools, faces, room layout, and a
viewer trajectory can make the scene feel less plausible or harder to explore.
If Method A is correctly oriented and Method B is mirrored, ratings can measure
orientation mismatch or semantic plausibility rather than reconstruction
quality. That biases a comparison across generation/reconstruction methods.

## Recommendation

1. For within-method ablations, retain only groups whose variants all share the
   same orientation; record the orientation flag and analyse those groups
   separately.
2. For cross-method results, normalize geometry and camera orientation to one
   documented convention before evaluation, or exclude mirrored
   index-method pairs from the common comparison set.
3. Keep an orientation audit table per `(method, index)`; do not infer it only
   from a camera determinant.
4. Run a small blinded pilot using an otherwise identical normal/mirrored pair
   to measure whether the chosen MOS dimensions are sensitive to mirroring.
