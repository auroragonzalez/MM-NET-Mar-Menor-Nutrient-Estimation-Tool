#!/usr/bin/env bash
# run_dev.sh — Launch the NEREIDAS+ web service (self-contained deployment).
# Everything (code, data, venv) lives inside the web_service/ directory.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# ── Data directory (inside web_service/) ────────────────────────────────────
export NEREIDAS_DATA_DIR="${NEREIDAS_DATA_DIR:-${SCRIPT_DIR}/data}"
export RESULTS_OUTPUT_DIR="${RESULTS_OUTPUT_DIR:-${SCRIPT_DIR}/data}"
export SCRAPER_INTERVAL_HOURS="${SCRAPER_INTERVAL_HOURS:-6}"

mkdir -p "${RESULTS_OUTPUT_DIR}"

echo "NEREIDAS_DATA_DIR=${NEREIDAS_DATA_DIR}"
echo "RESULTS_OUTPUT_DIR=${RESULTS_OUTPUT_DIR}"

# ── Python virtual environment ──────────────────────────────────────────────
VENV_DIR="${SCRIPT_DIR}/.venv"
if [ ! -f "${VENV_DIR}/bin/activate" ]; then
    echo "Creating virtual environment at ${VENV_DIR} ..."
    python3 -m venv "${VENV_DIR}"
    echo "Installing dependencies ..."
    "${VENV_DIR}/bin/pip" install -r requirements.txt --quiet
    echo "Dependencies installed."
fi

echo "Activating venv ..."
source "${VENV_DIR}/bin/activate"

# ── Launch ──────────────────────────────────────────────────────────────────
echo "Starting uvicorn on http://0.0.0.0:8000 ..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
