# Why must I start a local CLI command before opening the Chrome URL?

## Question

Why did the previously working streaming workflow require a command in the
local CLI before opening Chrome?

## Answer

The command starts NVIDIA's Web Viewer Sample on the machine that runs Chrome:

```bash
cd web-viewer-sample
npm install                 # only the first time
npm run dev
```

Then open `http://localhost:5173/` in Chrome on that same machine.  Select
**UI for any streaming app** and click **Next**.

Before `npm run dev`, set `stream.config.json` for the remote Kit server:

```json
"server": "140.113.214.34",
"signalingPort": 49100,
"mediaPort": null
```

Kit still runs remotely in the `kit-app-template` tmux session.  Its TCP
signal port is `49100` and its UDP media port is `47998`; both must be
reachable from the Chrome machine.
