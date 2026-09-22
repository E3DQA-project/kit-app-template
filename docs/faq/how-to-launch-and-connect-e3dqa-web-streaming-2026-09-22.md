# How do I launch and connect to E3DQA Web Streaming?

## Question

How do I start the E3DQA streaming app and connect to it remotely? Which URL
should I open in a browser?

## Answer

### Start the app

Run the streaming entry point from the `kit-app-template` tmux session after
activating the `pierce_base` conda environment:

```bash
cd /mnt/gen5_SSD/pierce/kit-app-template-e3dqa-web-streaming
conda activate pierce_base
./repo.sh launch nycu.e3dqa_scene_viewer_streaming.kit
```

The normal launcher requires a completed `repo.sh build`. During the initial
experiment, the repository's full precache was blocked before it reached the
streaming app, so the already-downloaded Kit runtime was used directly instead:

```bash
./_build/linux-x86_64/release/kit/kit \
  source/apps/nycu.e3dqa_scene_viewer_streaming.kit \
  --portable --ext-folder source/extensions --ext-folder source/apps \
  --/app/extensions/registryEnabled=1 --/app/enableStdoutOutput=1
```

Wait for these log messages before connecting:

```text
Started primary stream server on signal port 49100 and stream port 47998
app ready
```

### Connect

The present layer exposes a WebRTC signaling endpoint, not a browser page:

```text
ws://140.113.214.34:49100
```

Use that endpoint and UDP media port `47998` with a compatible Omniverse
WebRTC client. Do **not** type the WebSocket endpoint into a browser address
bar as though it were an HTTP URL.

For a directly browsable page such as `http://140.113.214.34:8011`, add the
separate `omni.services.livestream.webrtc` extension and its HTTP transport
configuration to the streaming layer. That service hosts NVIDIA's browser
client UI and discovers the configured primary stream automatically. It is not
enabled in the current minimal layer.

### Network checklist

- TCP `49100`: WebRTC signaling.
- UDP `47998`: WebRTC media.
- If the browser-client service is enabled: TCP `8011` (or the configured HTTP
  port).
- The firewall/NAT must permit the relevant ports to the host.
