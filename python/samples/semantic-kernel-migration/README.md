# Semantic Kernel Migration Samples

## Goal
Document concrete orchestrations that translate Python Semantic Kernel workflows to Agent Framework equivalents without importing the Semantic Kernel SDK into the core workspace.

## Layout
- `pyproject.toml`: Defines dependencies scoped to this folder, including `semantic-kernel` and local path links to Agent Framework packages.
- `orchestrations/sequential.py`: Sequential orchestration example migrated from Semantic Kernel.

## Prerequisites
- Python 3.10 or later.
- `uv` CLI installed (`pip install uv` or follow https://github.com/astral-sh/uv#installation).

## Environment Isolation
1. `cd samples/semantic-kernel-migration`
2. `uv venv --python 3.10 .venv-migration`
3. `source .venv-migration/bin/activate`
4. `uv sync`
   - Pulls `semantic-kernel` only inside this sandbox.
   - Resolves Agent Framework packages from the repo via local paths.

Deactivate with
```
deactivate
```

## Running the Samples
Within the activated `.venv-migration`:
```
uv run python orchestrations/sequential.py
```
Optionally replace the script path with any additional migration orchestrations you add under `orchestrations/`.

## Updating Dependencies
- Modify `pyproject.toml` as needed for new samples.
- Re-run `uv sync` to apply changes within the sandbox.

## Notes
- The root project `.venv` and dependency graph remain untouched.
- Keep new artifacts confined to this directory when expanding migration coverage.
