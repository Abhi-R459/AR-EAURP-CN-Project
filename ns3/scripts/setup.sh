#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/../.." && pwd)"
ns3_home="${NS3_HOME:-$HOME/.cache/ar-eaurp/ns-3.45}"
download=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --home) ns3_home="$2"; shift 2 ;;
    --download) download=1; shift ;;
    *) echo 'Usage: setup.sh [--home /path/to/ns-3.45] [--download]' >&2; exit 2 ;;
  esac
done
if [[ ! -f "$ns3_home/ns3" ]]; then
  if [[ $download != 1 ]]; then
    echo "ns-3 absent at $ns3_home; add --download to fetch ns-3.45." >&2
    exit 2
  fi
  if [[ -e "$ns3_home" ]]; then
    echo "Refusing to replace an existing directory: $ns3_home" >&2
    exit 2
  fi
  staging_dir="$(mktemp -d)"
  trap 'rm -rf "$staging_dir"' EXIT
  curl -fL --retry 3 https://www.nsnam.org/releases/ns-3.45.tar.bz2 -o "$staging_dir/ns3.tar.bz2"
  tar -xjf "$staging_dir/ns3.tar.bz2" -C "$staging_dir"
  mkdir -p "$(dirname "$ns3_home")"
  mv "$staging_dir/ns-3.45" "$ns3_home"
fi
ns3_home="$(cd "$ns3_home" && pwd)"
if [[ "$(cat "$ns3_home/VERSION")" != 3.45 ]]; then
  echo 'This module requires ns-3.45.' >&2; exit 2
fi
for relative in contrib/ar-eaurp scratch/ar-eaurp-sim.cc scratch/ar-eaurp-range.cc scratch/ar-eaurp-experiments.cc; do
  source_path="$project_root/ns3/$relative"
  target_path="$ns3_home/$relative"
  if [[ -L "$target_path" && "$target_path" -ef "$source_path" ]]; then continue; fi
  if [[ -e "$target_path" || -L "$target_path" ]]; then
    echo "Refusing to replace unrelated ns-3 content: $target_path" >&2; exit 2
  fi
  mkdir -p "$(dirname "$target_path")"
  ln -s "$source_path" "$target_path"
done
cd "$ns3_home"
# Use CMake directly: Colab runs as root, which the ns3 convenience launcher
# refuses. No privilege or system-user changes are needed for a normal build.
# csma and point-to-point are dependencies of upstream ns-3 test suites.
cmake -S . -B cmake-cache -DCMAKE_BUILD_TYPE=release -DNS3_NATIVE_OPTIMIZATIONS=ON \
  -DNS3_ASSERT=OFF -DNS3_LOG=OFF -DNS3_TESTS=ON -DNS3_EXAMPLES=OFF \
  -DNS3_ENABLED_MODULES=ar-eaurp,aodv,flow-monitor,netanim,csma,point-to-point
build_jobs="${NS3_JOBS:-4}"
cmake --build cmake-cache --parallel "$build_jobs" --target scratch_ar-eaurp-sim scratch_ar-eaurp-experiments scratch_ar-eaurp-range test-runner
"$ns3_home/build/scratch/ns3.45-ar-eaurp-experiments-optimized" --stamp=1 --project="$project_root" --ns3-home="$ns3_home"
printf 'Built ns-3.45 at %s\n' "$ns3_home"
