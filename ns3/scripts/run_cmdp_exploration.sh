#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/../.." && pwd)"
ns3_home="${NS3_HOME:-$HOME/.cache/ar-eaurp/ns-3.45}"
native="$ns3_home/build/scratch/ns3.45-ar-eaurp-sim-optimized"
out="${1:-$project_root/results/optimization_study/exploration_tuning}"
first_run="${2:-6}"
last_run="${3:-10}"
mode="${4:-both}"

if [[ ! -x "$native" ]]; then
  echo "Build first: bash ns3/scripts/setup.sh" >&2
  exit 2
fi
mkdir -p "$out"

for run in $(seq "$first_run" "$last_run"); do
  common=(--attack=grayhole --malicious=0.25 --nodes=24 --flows=6
          --area=420 --time=120 --warmup=20 --seed=1 --run="$run"
          --protocol=ar-eaurp --train=1 --commission=240
          --ganEpochs=120 --lstmEpochs=30)
  if [[ "$mode" == "both" || "$mode" == "low" ]]; then
    "$native" "${common[@]}" --cmdpEpsStart=0.05 --cmdpEpsEnd=0.01 \
      --json="$out/ar-low-exploration-r${run}.json" \
      >"$out/ar-low-exploration-r${run}.log" 2>&1
  fi
  if [[ "$mode" == "both" || "$mode" == "greedy" ]]; then
    "$native" "${common[@]}" --cmdpEpsStart=0 --cmdpEpsEnd=0 \
      --json="$out/ar-greedy-r${run}.json" \
      >"$out/ar-greedy-r${run}.log" 2>&1
  fi
  echo "Completed exploration ablations for matched run $run"
done
