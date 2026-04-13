#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TVL_ROOT="$(cd "${ROOT_DIR}/../.." && pwd)"
PYTHONPATH_VALUE="${TVL_ROOT}/python:${TVL_ROOT}"
SPEC="${ROOT_DIR}/ch1_motivation_experiment.tvl.yml"
MANIFEST="${ROOT_DIR}/ch5_integration_manifest.yaml"
DVL_SUITE="${ROOT_DIR}/ch5_dvl_suite.json"

run_tvl_tool() {
  local module_path="$1"
  shift
  PYTHONPATH="${PYTHONPATH_VALUE}" python3 -m "${module_path}" "$@"
}

echo "[validate] Checking spec..."
run_tvl_tool tvl_tools.tvl_validate.cli "${SPEC}"

echo "[structural] Checking structural satisfiability..."
run_tvl_tool tvl_tools.tvl_check_structural.cli "${SPEC}"

echo "[operational] Checking budgets and derived constraints..."
run_tvl_tool tvl_tools.tvl_check_operational.cli "${SPEC}"

echo "[triagent] Dry-running pipeline..."
if command -v triagent >/dev/null 2>&1; then
  triagent deploy --dry-run campus-orientation-rag
else
  echo "  skipped: triagent CLI not installed in this repo environment"
  echo "  example command: triagent deploy --dry-run campus-orientation-rag"
fi

echo "[dvl] Running validation suites..."
if command -v dvl >/dev/null 2>&1; then
  dvl validate "${DVL_SUITE}"
else
  echo "  skipped: dvl CLI not installed in this repo environment"
  echo "  example command: dvl validate ${DVL_SUITE}"
fi

echo "[manifest] Capturing manifest..."
cat "${MANIFEST}"
