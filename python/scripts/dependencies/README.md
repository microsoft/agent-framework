# Dependency Scripts

This folder contains the Python workspace tooling for dependency maintenance:

- validating runtime dependency lower and upper bounds
- refreshing exact dev dependency pins
- writing dependency validation reports for local runs and workflows

Run the commands below from the `python/` directory.

## Files in this folder

- `validate_dependency_bounds.py`
  - Main entrypoint for dependency-bound workflows.
  - Supports `test`, `lower`, `upper`, and `both` modes.
  - `test` runs workspace-wide smoke validation at the lower and upper ends of the currently allowed ranges.
  - `lower`, `upper`, and `both` dispatch to the lower/upper optimizer implementations for one package.

- `upgrade_dev_dependencies.py`
  - Refreshes exact dev dependency pins across the root `pyproject.toml` and package `pyproject.toml` files.
  - Reuses the same version-selection logic as the upper-bound tooling so direct dev-tooling refreshes and dependency-range expansion stay consistent.

- `_dependency_bounds_lower_impl.py`
  - Package-scoped lower-bound optimizer.
  - Tries older dependency versions within the currently allowed line and keeps the oldest passing lower bound.
  - Writes `dependency-lower-bound-results.json` in this folder by default.

- `_dependency_bounds_upper_impl.py`
  - Package-scoped upper-bound optimizer.
  - Tries newer dependency versions within candidate lines and keeps the newest passing upper bound.
  - Also contains shared parsing/rewrite helpers reused by `upgrade_dev_dependencies.py`.
  - Writes `dependency-range-results.json` in this folder by default.

- `_dependency_bounds_runtime.py`
  - Shared helper used by the validators to build isolated `uv run` commands.
  - Reattaches the repo-wide toolchain (`ruff`, `pyright`, `pytest`, `poethepoet`, and related helpers) inside temporary environments so package tasks behave the same way they do in the workspace.


## Common entrypoints

### Poe tasks

These are the normal user-facing entrypoints:

```bash
uv run poe upgrade-dev-dependency-pins
uv run poe upgrade-dev-dependencies
uv run poe validate-dependency-bounds-test
uv run poe validate-dependency-bounds-test --package core
uv run poe validate-dependency-bounds-project --mode both --package core --dependency "<dependency-name>"
```

- `upgrade-dev-dependency-pins` only refreshes exact dev pins in `pyproject.toml` files.
- `upgrade-dev-dependencies` refreshes dev pins (using task above), runs `uv lock --upgrade`, reinstalls from the frozen lockfile, then runs `check`, `typing`, and `test`.
- `validate-dependency-bounds-test` runs the repo-wide lower/upper smoke gate.
- `validate-dependency-bounds-project` is the single package-scoped task; use `--mode lower`, `--mode upper`, or `--mode both` for the target package/dependency pair. Its `--package` argument defaults to `*`, and `--dependency` is optional, so automation can also use it for repo-wide upper-bound runs.

### GitHub Actions workflows

These workflows call the Poe tasks:

- `.github/workflows/python-dependency-range-validation.yml`
  - Trigger: `workflow_dispatch`
  - Runs `uv run poe validate-dependency-bounds-project --mode upper --package "*"`
  - Uploads `python/scripts/dependencies/dependency-range-results.json`
  - Creates issues for failing candidate versions and opens/updates a PR for passing range updates

- `.github/workflows/python-dev-dependency-upgrade.yml`
  - Trigger: `workflow_dispatch`
  - Runs `uv run poe upgrade-dev-dependencies`
  - Commits any resulting `pyproject.toml` / `uv.lock` changes and opens/updates a PR

### Direct module execution

These are useful for debugging or targeted manual runs:

```bash
python -m scripts.dependencies.upgrade_dev_dependencies --dry-run --version-source lock
python -m scripts.dependencies.validate_dependency_bounds --mode test --package core --dry-run
python -m scripts.dependencies.validate_dependency_bounds --mode both --package core --dependencies openai --dry-run
python -m scripts.dependencies._dependency_bounds_lower_impl --packages core --dependencies openai --dry-run
python -m scripts.dependencies._dependency_bounds_upper_impl --packages core --dependencies openai --dry-run
```

Use the direct lower/upper implementation modules mainly for debugging or development of the optimizers themselves. For normal usage, prefer the Poe tasks or `validate_dependency_bounds.py`.

## Generated report files

The validators write JSON reports into this folder:

- `dependency-bounds-test-results.json`
- `dependency-lower-bound-results.json`
- `dependency-range-results.json`

These report files are ignored by git.
