#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/../.." && pwd)"
ns3_home="${NS3_HOME:-$HOME/.cache/ar-eaurp/ns-3.45}"
native="$ns3_home/build/scratch/ns3.45-ar-eaurp-experiments-optimized"
if [[ ! -x "$native" ]]; then
  echo 'Build first: bash ns3/scripts/setup.sh --download' >&2; exit 2
fi
export AR_EAURP_PROJECT="$project_root"
export NS3_HOME="$ns3_home"
exec "$native" "$@"
