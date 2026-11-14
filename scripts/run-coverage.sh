#!/usr/bin/env bash
# Run backend and frontend coverage and enforce the gates.
#
#   scripts/run-coverage.sh            # measure + enforce
#   scripts/run-coverage.sh --update-baseline
#
# Reports:
#   coverage/backend/               coverage.py XML + HTML
#   coverage/frontend/              Vitest json-summary + HTML
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p coverage/backend coverage/frontend

run_backend() {
    echo "=== Backend coverage ==="
    local pytest_args=(
        tests/unit
        -q
        --cov
        --cov-config=.coveragerc
        --cov-report=term
        --cov-report=xml:coverage/backend/coverage.xml
        --cov-report=html:coverage/backend/html
    )

    if command -v pytest >/dev/null 2>&1 && python3 -c "import pytest_cov" >/dev/null 2>&1; then
        PYTHONPATH=src/backend pytest "${pytest_args[@]}"
    else
        echo "Local pytest/pytest-cov not available; running in python:3.11-slim."
        docker run --rm -v "$ROOT_DIR:/app" -w /app -e PYTHONPATH=src/backend python:3.11-slim \
            sh -c "pip install -q -r requirements-dev.txt -r src/backend/requirements.txt && pytest $(printf '%q ' "${pytest_args[@]}")"
    fi
}

run_frontend() {
    echo "=== Frontend coverage ==="
    if [[ ! -d src/frontend/node_modules ]]; then
        echo "src/frontend/node_modules is missing; run 'npm ci' in src/frontend first." >&2
        exit 1
    fi
    (cd src/frontend && npm run test:coverage)
}

run_backend
run_frontend

echo "=== Coverage gates ==="
python3 scripts/check-coverage.py "$@"

echo "Reports: coverage/backend/html/index.html, coverage/frontend/index.html"
