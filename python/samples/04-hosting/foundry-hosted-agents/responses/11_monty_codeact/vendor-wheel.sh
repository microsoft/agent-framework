#!/usr/bin/env bash
# Vendor the alpha agent-framework-monty wheel into ./wheels/ so the
# Dockerfile (which calls `uv sync`) can resolve it offline.
#
# Required because agent-framework-monty is not yet on PyPI - see
# pyproject.toml `[tool.uv.sources]`.
#
# Run from this directory:
#   ./vendor-wheel.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../../../../../.." && pwd)"
MONTY_DIR="${REPO_ROOT}/python/packages/monty"
WHEEL_OUT="${HERE}/wheels"

if [ ! -d "${MONTY_DIR}" ]; then
    echo "Error: cannot find ${MONTY_DIR}" >&2
    exit 1
fi

mkdir -p "${WHEEL_OUT}"
echo "Building agent-framework-monty wheel from ${MONTY_DIR}"
echo "Output: ${WHEEL_OUT}"
(cd "${REPO_ROOT}/python" && uv build "packages/monty" -o "${WHEEL_OUT}")
echo "Done."
ls -la "${WHEEL_OUT}"
