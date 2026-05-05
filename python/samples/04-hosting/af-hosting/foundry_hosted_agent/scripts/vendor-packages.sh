#!/usr/bin/env bash
# Vendors the workspace packages this sample depends on into ./_vendor/ so
# the Docker build context (which is this folder, per azure.yaml) is
# self-contained. Run this once after cloning the repo, and again whenever
# you edit a workspace package and want the changes reflected in the next
# `uv sync` / `docker build` / `azd deploy`.
#
# `azd` invokes this automatically via the `prepackage` hook in azure.yaml.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$HERE/../../../../.." && pwd)"  # python/
VENDOR="$HERE/../_vendor"

PACKAGES=(
  foundry_hosting
  hosting
  hosting-invocations
  hosting-responses
)

mkdir -p "$VENDOR"

for pkg in "${PACKAGES[@]}"; do
  src="$WORKSPACE_ROOT/packages/$pkg"
  dst="$VENDOR/$pkg"
  if [[ ! -d "$src" ]]; then
    echo "ERROR: workspace package not found: $src" >&2
    exit 1
  fi
  rm -rf "$dst"
  rsync -aL \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache/' \
    --exclude '.mypy_cache/' \
    --exclude '.ruff_cache/' \
    --exclude 'dist/' \
    --exclude 'build/' \
    --exclude '*.egg-info/' \
    "$src/" "$dst/"
  echo "vendored packages/$pkg -> _vendor/$pkg"
done
