#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/../.." && pwd)"
ns3_home="${NS3_HOME:-$HOME/.cache/ar-eaurp/ns-3.45}"
native="$ns3_home/build/scratch/ns3.45-ar-eaurp-experiments-optimized"
"$ns3_home/build/utils/ns3.45-test-runner-optimized" --suite=ar-eaurp --verbose
bash "$project_root/ns3/scripts/run.sh" --verify=1
test_directory="$(mktemp -d)"
trap 'rm -rf "$test_directory"' EXIT
mkdir -p "$test_directory/wrong-home/build/scratch"
if "$native" --project="$project_root" --ns3-home="$test_directory/wrong-home" --verify=1 > "$test_directory/wrong.log" 2>&1; then
  echo 'FAIL cross-install identity accepted' >&2; exit 1
fi
[[ "$(cat "$test_directory/wrong.log")" == *'does not match the running native executable'* ]]
echo 'PASS cross-install identity rejected'
mkdir -p "$test_directory/stale-project"
cp -R "$project_root/ns3" "$test_directory/stale-project/ns3"
printf '\n// Deliberately stale source for the provenance test.\n' >> "$test_directory/stale-project/ns3/scratch/ar-eaurp-sim.cc"
if "$native" --project="$test_directory/stale-project" --ns3-home="$ns3_home" --verify=1 > "$test_directory/stale.log" 2>&1; then
  echo 'FAIL changed source accepted' >&2; exit 1
fi
[[ "$(cat "$test_directory/stale.log")" == *'stale or unrecorded'* ]]
echo 'PASS stale source rejected'
bash "$project_root/ns3/scripts/run.sh" --profile=smoke --only=e6 --out="$test_directory/output with spaces (native)" > "$test_directory/path.log" 2>&1
[[ -s "$test_directory/output with spaces (native)/report.html" ]]
[[ "$(cat "$test_directory/output with spaces (native)/report.md")" == *'](<'*'output with spaces (native)'* ]]
echo 'PASS native plots/reports support spaced output paths'
echo 'Native workflow verification completed'
