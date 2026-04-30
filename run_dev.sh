#!/usr/bin/env bash
# run_dev.sh — Launch the NEREIDAS+ web service locally for development.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# Use repository-local paths instead of container /data paths
export NEREIDAS_DATA_DIR="${REPO_ROOT}/NEREIDAS+"
export RESULTS_OUTPUT_DIR="${REPO_ROOT}/web_service/data"
export SCRAPER_INTERVAL_HOURS="6"

mkdir -p "${RESULTS_OUTPUT_DIR}"

echo "NEREIDAS_DATA_DIR=${NEREIDAS_DATA_DIR}"
echo "RESULTS_OUTPUT_DIR=${RESULTS_OUTPUT_DIR}"
echo "Activating venv ..."
source .venv/bin/activate

echo "Starting uvicorn ..."
cd "${REPO_ROOT}/web_service"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
