#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/../.." && pwd)"
ns3_home="${NS3_HOME:-$HOME/.cache/ar-eaurp/ns-3.45}"
native="$ns3_home/build/scratch/ns3.45-ar-eaurp-sim-optimized"
out="${1:-$project_root/results/optimization_study/tuning}"
first_run="${2:-6}"
last_run="${3:-10}"

if [[ ! -x "$native" ]]; then
  echo "Build first: bash ns3/scripts/setup.sh" >&2
  exit 2
fi
mkdir -p "$out"

# Exploratory only: seeds 6-10 are reserved for tuning, separate from the
# previously reported runs 1-5. Confirm any selected change on new seeds.
for run in $(seq "$first_run" "$last_run"); do
  common=(--attack=grayhole --malicious=0.25 --nodes=24 --flows=6
          --area=420 --time=120 --warmup=20 --seed=1 --run="$run")
  "$native" "${common[@]}" --protocol=eaurp --train=0 \
    --json="$out/eaurp-r${run}.json" >"$out/eaurp-r${run}.log" 2>&1
  "$native" "${common[@]}" --protocol=ar-eaurp --train=1 --commission=240 \
    --ganEpochs=120 --lstmEpochs=30 \
    --json="$out/ar-default-r${run}.json" >"$out/ar-default-r${run}.log" 2>&1
  "$native" "${common[@]}" --protocol=ar-eaurp --train=1 --commission=240 \
    --ganEpochs=120 --lstmEpochs=30 --cmdp=0 \
    --json="$out/ar-no-cmdp-r${run}.json" >"$out/ar-no-cmdp-r${run}.log" 2>&1
  echo "Completed matched tuning run $run"
done
