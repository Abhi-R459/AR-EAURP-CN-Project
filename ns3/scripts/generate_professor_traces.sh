#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/../.." && pwd)"
ns3_home="${NS3_HOME:-$HOME/.cache/ar-eaurp/ns-3.45}"
native="$ns3_home/build/scratch/ns3.45-ar-eaurp-sim-optimized"
out_root="${1:-$project_root/results/ns3-live/professor-demo/protocol-matrix}"

if [[ ! -x "$native" ]]; then
  echo "Native simulator not found: $native" >&2
  echo "Build ns-3 first with: bash ns3/scripts/setup.sh" >&2
  exit 2
fi

protocols=(ar-eaurp drl-senior drl-paper eaurp aodv)
attacks=(grayhole blackhole trust_poisoning)

run_case() {
  local protocol="$1" attack="$2" hostile="$3" scenario="$4"
  local out="$out_root/$protocol/$scenario"
  local trace="$out/trace.xml" result="$out/result.json"
  mkdir -p "$out"
  local args=(
    "--protocol=$protocol" "--attack=$attack" "--malicious=$hostile"
    --nodes=24 --flows=6 --time=25 --warmup=5 --area=420
    --seed=1 --run=1 "--netanim=$trace" --realtime=1 --train=1
    "--json=$result"
  )

  if [[ -s "$result" && -s "$trace" ]]; then
    echo "SKIP existing $protocol / $scenario"
    return
  fi

  python3 - "$out/launch.json" "$native" "$protocol" "$attack" "$hostile" "$trace" "$result" "${args[@]}" <<'PY'
import json, sys
path, binary, protocol, attack, hostile, trace, result, *args = sys.argv[1:]
metadata = {
    "requested_settings": {
        "protocol": protocol, "attack": attack, "nodes": 24, "flows": 6,
        "malicious": float(hostile), "duration": 25, "warmup": 5,
        "area": 420, "seed": 1, "run": 1, "realtime": True, "train": True,
    },
    "command": [binary, *args],
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(metadata, f, indent=2)
    f.write("\n")
PY

  echo "RUN $protocol / $scenario"
  if ! AR_EAURP_PROJECT="$project_root" NS3_HOME="$ns3_home" \
      "$native" "${args[@]}" >"$out/simulator.log" 2>&1; then
    echo "FAILED $protocol / $scenario; see $out/simulator.log" >&2
    return 1
  fi
}

for protocol in "${protocols[@]}"; do
  for attack in "${attacks[@]}"; do
    run_case "$protocol" "$attack" 0.35 "$attack"
  done
done

# Upstream ns-3 AODV is restricted to a clean, zero-hostile run in this project.
run_case ns3-aodv none 0 clean

echo "Protocol matrix complete: $out_root"
