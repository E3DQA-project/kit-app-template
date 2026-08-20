#!/usr/bin/env bash
set -u

output_dir="${1:-_mos_asset_loading_experiment/mos-gap-capture}"
scene_list="${2:?usage: $0 OUTPUT_DIR SCENE_LIST_JSON}"
mkdir -p "$output_dir"

export DISPLAY="${DISPLAY:-:1}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1005}"

gpu_csv="$output_dir/gpu.csv"
kit_log="$output_dir/kit.stdout.log"

if command -v nvidia-smi >/dev/null 2>&1; then
    timeout 90s nvidia-smi \
        --query-gpu=timestamp,index,name,utilization.gpu,memory.used,power.draw,clocks.gr,clocks.sm \
        --format=csv,noheader,nounits -lms 250 >"$gpu_csv" 2>/dev/null &
    gpu_pid=$!
else
    gpu_pid=""
fi

set +e
./repo.sh launch nycu.mos_app.kit -- \
    --/exts/nycu.mos_app_extension/sceneListPath="$scene_list" \
    --/exts/nycu.my_usd_viewer_messaging_extension/sceneLoadingActivityCapture=true \
    --/exts/nycu.my_usd_viewer_messaging_extension/sceneLoadingNvtxCapture=true \
    >"$kit_log" 2>&1
kit_status=$?
set -e

if [[ -n "$gpu_pid" ]]; then
    kill "$gpu_pid" 2>/dev/null || true
    wait "$gpu_pid" 2>/dev/null || true
fi

printf 'kit_exit=%s\n' "$kit_status" >"$output_dir/result.txt"
printf 'gpu_csv=%s\nkit_log=%s\n' "$gpu_csv" "$kit_log" >>"$output_dir/result.txt"
exit "$kit_status"
