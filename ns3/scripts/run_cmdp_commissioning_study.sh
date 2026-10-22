#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/../.." && pwd)"
ns3_home="${NS3_HOME:-$HOME/.cache/ar-eaurp/ns-3.45}"
native="$ns3_home/build/scratch/ns3.45-ar-eaurp-sim-optimized"
out="${1:-$project_root/results/optimization_study/cmdp_commissioning_holdout}"
first_run="${2:-21}"
last_run="${3:-30}"

if [[ ! -x "$native" ]]; then
  echo "Build first: bash ns3/scripts/setup.sh" >&2
  exit 2
fi
mkdir -p "$out"

for run in $(seq "$first_run" "$last_run"); do
  common=(--attack=grayhole --malicious=0.25 --nodes=24 --flows=6
          --area=420 --time=120 --warmup=20 --seed=1 --run="$run")
  "$native" "${common[@]}" --protocol=eaurp --train=0 \
    --json="$out/eaurp-r${run}.json" >"$out/eaurp-r${run}.log" 2>&1
  "$native" "${common[@]}" --protocol=ar-eaurp --train=1 --commission=240 \
    --ganEpochs=120 --lstmEpochs=30 \
    --json="$out/ar-commission-trained-r${run}.json" \
    >"$out/ar-commission-trained-r${run}.log" 2>&1
  echo "Completed commissioning-trained matched run $run"
done
