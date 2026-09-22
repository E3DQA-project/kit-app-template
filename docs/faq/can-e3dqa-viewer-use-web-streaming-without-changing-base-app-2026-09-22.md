# Can the E3DQA viewer use Web Streaming without changing the base app?

## Question

Can `kit-app-template` provide the same remote browser access as
`kit-app-template-e3dqa-streaming-fix` while retaining its current application
and connection-related functionality?

## Answer

Yes. The repository now has a separate
`nycu.e3dqa_scene_viewer_streaming.kit` application layer. It depends on the
unchanged `nycu.e3dqa_scene_viewer` desktop app and adds only the Kit WebRTC
livestream host configuration. It uses the confirmed deployment endpoint:
`140.113.214.34`, signalling port `49100`, and media port `47998`.

The streaming entry point is registered with `repo_precache_exts.apps`, so it
is built alongside the desktop app. Remote clients still require these ports to
be reachable through the deployment host's firewall and NAT.
