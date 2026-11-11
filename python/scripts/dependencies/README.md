# Dependency Scripts

This folder contains the Python workspace tooling for dependency maintenance:

- validating runtime dependency lower and upper bounds
- refreshing exact dev dependency pins
- writing dependency validation reports for local runs and workflows

Run the commands below from the `python/` directory.

## Files in this folder

- `validate_dependency_bounds.py`
  - Main entrypoint for dependency-bound workflows.
  - Supports `release`, `test`, `lower`, `upper`, and `both` modes.
  - `release` refreshes `uv.lock`, then runs changed packages through fast lock-independent lower/upper import probes.
  - `test` runs the exhaustive workspace test+typing compatibility matrix.
  - `lower`, `upper`, and `both` dispatch to the lower/upper optimizer implementations for one package.

- `detect_version_bumps.py`
  - Dependency-free CI selector requiring Python 3.11 or newer.
  - Compares committed `project.version` values against an explicit base commit for the root package and existing
    workspace members, and compares workspace membership at both commits. Newly added package manifests and existing
    packages newly included through `members` or `exclude` changes require validation, even without a version change.
  - Other metadata edits, deleted packages, and excluded standalone projects do not trigger it.
  - Treats any version value change, including a downgrade, as requiring validation.
  - Invalid base refs or malformed version metadata fail detection instead of silently skipping the gate.

- `_dependency_bounds_release_impl.py`
  - Discovers package metadata changed from the selected release base.
  - Verifies that every Agent Framework integration in `agent-framework-core[all]` has lower and upper bounds, and
    that workspace integrations use their current release version as the lower bound.
  - Resolves published runtime dependencies and non-development extras independently of `uv.lock` with both
    `lowest-direct` and `highest` strategies.
  - Derives the minimum supported Python minor from each changed package's internal editable dependency closure.
  - Re-declares any pre-release-bounded external requirement found in that closure as a direct probe requirement and
    runs isolated probes with `prerelease = "if-necessary"`.
  - Imports each changed package and records resolved dependency versions in a JSON report.
  - Runs probes concurrently under one five-minute deadline.

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
  - Resolves internal editable packages from the target's enabled groups and extras, following only base transitive
    dependencies and explicitly requested extras so aggregate surfaces such as `core[all]` do not leak into unrelated
    package probes.
  - Uses a package-defined `dependency-pyright` task when present, allowing dependency probes to type-check the
    package implementation without requiring optional lazy namespace packages. Normal repository Pyright tasks are
    unchanged. These tasks reuse the root workspace development requirements inside their isolated environment.


## Common entrypoints

### Poe tasks

These are the normal user-facing entrypoints:

```bash
uv run poe upgrade-dev-dependency-pins
uv run poe upgrade-dev-dependencies
uv run poe validate-python-release --base-ref upstream/main
uv run poe validate-dependency-bounds-test
uv run poe validate-dependency-bounds-test --package core
uv run poe validate-dependency-bounds-project --mode both --package core --dependency "<dependency-name>"
```

- `upgrade-dev-dependency-pins` refreshes exact development pins in
  `pyproject.toml` files and on-demand tool pins under
  `tooling/`.
- `upgrade-dev-dependencies` refreshes those pins, runs `uv lock --upgrade`,
  reinstalls from the frozen lockfile, then runs `check` and `typing`.
- `validate-python-release` is the bounded release gate: it refreshes `uv.lock`, finds changed package metadata,
  and probes both dependency-bound extremes without reusing the lockfile.
- `validate-dependency-bounds-test` runs the exhaustive package test+typing matrix and is intentionally not part of
  the routine local release-preparation path. Version-bump and new-package PRs run it as a blocking CI check.
- `validate-dependency-bounds-project` is the single package-scoped task; use `--mode lower`, `--mode upper`, or `--mode both` for the target package/dependency pair. Its `--package` argument defaults to `*`, and `--dependency` is optional, so automation can also use it for repo-wide upper-bound runs.

### GitHub Actions workflows

These workflows call the Poe tasks:

- `.github/workflows/python-dependency-bounds.yml`
  - `Dependency Bounds Validation` is blocking on PRs and merge groups containing a new workspace package or an existing
    package version change; ordinary PRs run only the lightweight selector and its offline regression tests,
    without installing the workspace.
  - Compares the checked-out synthetic merge commit against the immutable PR `base.sha` or merge-group `base_sha`,
    not a moving branch or the previous commit. Manual dispatch explicitly runs the full matrix.
  - Runs `uv run --locked --group tool-runtime poe validate-dependency-bounds-test --package "*"` on Python 3.13,
    with a 60-minute job timeout and the validator's existing per-command timeouts and first-failure behavior.
  - Uploads `dependency-bounds-test-results.json` even on validation failure.
  - To enforce this gate at merge time, repository rules must require the `Dependency Bounds Validation` check.
    No new package or version change produces a successful no-op check; detector/setup/validation errors fail the check.
    The workflow has no PR path filter, so non-Python PRs also receive that successful no-op instead of a pending required check.
  - This does not substitute the bounded `validate-python-release` import probes for test-and-typing coverage.

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
uv run --locked --group tool-runtime python -m scripts.dependencies.upgrade_dev_dependencies --dry-run --version-source lock
uv run --locked --group tool-runtime python -m scripts.dependencies.validate_dependency_bounds --mode release --base-ref upstream/main --dry-run
uv run --locked --group tool-runtime python -m scripts.dependencies.validate_dependency_bounds --mode test --package core --dry-run
uv run --locked --group tool-runtime python -m scripts.dependencies.validate_dependency_bounds --mode both --package core --dependencies openai --dry-run
uv run --locked --group tool-runtime python -m scripts.dependencies._dependency_bounds_lower_impl --packages core --dependencies openai --dry-run
uv run --locked --group tool-runtime python -m scripts.dependencies._dependency_bounds_upper_impl --packages core --dependencies openai --dry-run
```

Use the direct lower/upper implementation modules mainly for debugging or development of the optimizers themselves. For normal usage, prefer the Poe tasks or `validate_dependency_bounds.py`.

## Generated report files

The validators write JSON reports into this folder:

- `dependency-bounds-test-results.json`
- `dependency-bounds-release-results.json`
- `dependency-lower-bound-results.json`
- `dependency-range-results.json`

These report files are ignored by git.
