#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./tools/show_stream_ports.sh [app_kit_name]
# Example:
#   ./tools/show_stream_ports.sh my_editor_1_streaming.kit
APP_KIT_NAME="${1:-my_editor_1_streaming.kit}"

PID="$(
    pgrep -af "$APP_KIT_NAME" 2>/dev/null \
    | awk '/\/kit\/kit/ {print $1; exit}' || true
)"

if [[ -z "${PID:-}" ]]; then
    echo "No running Kit process found for: $APP_KIT_NAME"
    echo "Start the app first, for example:"
    echo "  ./repo.sh launch $APP_KIT_NAME -- --no-window"
    exit 1
fi

echo "Found process: pid=$PID app=$APP_KIT_NAME"
echo
echo "Listening sockets owned by that process:"
ss -lntup | awk -v pid="$PID" '
NR==1 {next}
index($0, "pid=" pid ",") {
    if ($1 ~ /^tcp/) {
        print "  signalPort (TCP): " $5
    } else if ($1 ~ /^udp/) {
        print "  streamPort (UDP): " $5
    } else {
        print "  " $0
    }
    found=1
}
END {
    if (!found) {
        print "  (No listening TCP/UDP sockets found for this PID yet.)"
    }
}
'
