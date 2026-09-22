# How do I launch and connect to E3DQA Web Streaming?

## Question

How do I start the E3DQA streaming application and open it remotely in a
browser?

## Answer

This application follows the same architecture as
`kit-app-template-e3dqa-streaming-fix`: Kit hosts a WebRTC stream and NVIDIA's
separate Web Viewer Sample supplies the browser page.  Kit itself does not
serve a page on port 8011.

### Start Kit

Use the `kit-app-template` tmux session and launch the built application
without a local window:

```bash
tmux attach -t kit-app-template
cd /mnt/gen5_SSD/pierce/kit-app-template-e3dqa-web-streaming
conda activate pierce_base
./repo.sh build                 # needed after changing .kit or premake5.lua
./repo.sh launch nycu.e3dqa_scene_viewer_streaming.kit -- --no-window
```

Wait until the log says `app ready`.  The signal server must then listen on
TCP port `49100`:

```bash
ss -ltnp | rg ':49100'
```

### Open the browser client

For the current experiment, the official NVIDIA Web Viewer Sample is running
on this host.  Open this URL from a Chromium-based browser:

```text
http://140.113.214.34:5173/
```

Choose **UI for any streaming app**.  Its local-stream configuration connects
to `140.113.214.34:49100`, which is the running E3DQA Kit application.

### Required network ports

- TCP `5173`: Web Viewer Sample page for this shared-host experiment.
- TCP `49100`: Kit WebRTC signaling.
- UDP `47998`: Kit WebRTC media.

If the page is hosted elsewhere, configure that Web Viewer Sample's local
`server` field to `140.113.214.34`; the signal and media ports remain the
same.

### Stop the experiment

In the `kit-app-template` tmux pane, press `Ctrl-C` to stop Kit.  In the
`web-viewer-sample` tmux pane, press `Ctrl-C` to stop the Vite server.
