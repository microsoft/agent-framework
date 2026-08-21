---
name: python-package-management
description: >
  Guide for managing packages in the Agent Framework Python monorepo, including
  creating new connector packages, versioning, and the lazy-loading pattern.
  Use this when adding, modifying, or releasing packages.
---

# Python Package Management

## Monorepo Structure

```
python/
├── pyproject.toml              # Root package (agent-framework)
├── packages/
│   ├── core/                   # agent-framework-core (main package)
│   ├── foundry/                # agent-framework-foundry
│   ├── anthropic/              # agent-framework-anthropic
│   └── ...                     # Other connector packages
```

- `agent-framework-core` contains core abstractions and OpenAI/Azure OpenAI built-in
- Provider packages extend core with specific integrations
- Root `agent-framework` depends on `agent-framework-core[all]`

## Dependency Management

Uses [uv](https://github.com/astral-sh/uv) for dependency management and
[poethepoet](https://github.com/nat-n/poethepoet) for task automation.

```bash
# Full setup (venv + install + prek hooks)
uv run poe setup

# Install dependencies from lockfile (frozen resolution with prerelease policy)
uv run poe install

# Create venv with specific Python version
uv run poe venv --python 3.12

# Intentionally upgrade a specific dependency to reduce lockfile conflicts
uv lock --upgrade-package <dependency-name> && uv run poe install

# Refresh exact development dependency-group pins, lockfile, and validation in one run
uv run poe upgrade-dev-dependencies

# Release cuts: refresh uv.lock and probe changed packages at both bound extremes.
# The release probe has a shared five-minute deadline.
uv run poe validate-python-release --base-ref upstream/main

# Exhaustive test+typing matrix (slow; use for deliberate dependency-range work or CI)
uv run poe validate-dependency-bounds-test
# Defaults to --package "*"; scope locally whenever possible.
uv run poe validate-dependency-bounds-test --package core

# Then expand bounds for one dependency in the target package
uv run poe validate-dependency-bounds-project --mode both --package core --dependency "<dependency-name>"

# Repo-wide automation can reuse the same task
uv run poe validate-dependency-bounds-project --mode upper --package "*"

# Add a dependency to one project and run both validators for that project/dependency
uv run poe add-dependency-and-validate-bounds --package core --dependency "<dependency-spec>"
```

### Dependency Bound Notes

- Stable dependencies (`>=1.0`) should typically be bounded as `>=<known-good>,<next-major>`.
- Prerelease (`dev`/`a`/`b`/`rc`) and `<1.0` dependencies should use hard bounds with an explicit upper cap (avoid open-ended ranges).
- For `<1.0` dependencies, prefer the broadest validated range the package can really support. That may be a patch line, a minor line, or multiple minor lines when checks/tests show the broader lane is compatible.
- Prefer supporting multiple majors when practical; if APIs diverge across supported majors, use version-conditional imports/paths.
- For release-only version, lifecycle, pin, and internal-floor edits, use `validate-python-release`. It refreshes
  `uv.lock`, finds changed package metadata relative to the selected main ref, and runs the changed packages'
  published runtime dependencies and non-development extras through lock-independent `lowest-direct` and `highest`
  import probes on the minimum Python minor supported by each package's internal editable closure. The probes run
  concurrently under one 300-second deadline; pass `--python` only when an explicit interpreter override is needed.
- For deliberate external dependency-range changes, use
  `validate-dependency-bounds-project --mode both` for the target package/dependency to find and validate the actual
  minimum and maximum constraints. Scope the exhaustive `validate-dependency-bounds-test` matrix to affected
  packages during local iteration; reserve the workspace-wide form for CI or an intentional full audit. The same
  project task can drive repo-wide upper-bound automation by using `--package "*"` and omitting `--dependency`.
- Prefer targeted lock updates with `uv lock --upgrade-package <dependency-name>` to reduce `uv.lock` merge conflicts.
- Use `add-dependency-and-validate-bounds` for package-scoped dependency additions plus bound validation in one command.
- Keep shared tooling and source/type-check support in the root or package `dev` group. Put package-specific test
  fixtures in a `test` group, and use a feature-named group for local-only executable dependencies that cannot be
  expressed in published runtime metadata.
- Use `upgrade-dev-dependencies` for repo-wide development dependency refreshes; it repins exact dependencies
  across development groups, refreshes `uv.lock`, and reruns `check`, `typing`, and `test`.

## Lazy Loading Pattern

### Root core API

The root `agent_framework` package is a lazy public API surface:

- Runtime exports live in `packages/core/agent_framework/__init__.py`.
- Typing/editor exports live in `packages/core/agent_framework/__init__.pyi`.
- Add or move root exports in `_LAZY_MODULE_EXPORTS`, keep the explicit runtime `__all__` in sync, and add the same
  symbol to the `.pyi` file.
- Keep deprecation behavior in the owning module (for example, a module-level `__getattr__` that warns and returns
  the deprecated alias). Do not add one-off deprecated-symbol branches to root `__getattr__`.
- Validate root API changes with `uv run poe syntax -P core`, `uv run poe pyright -P core`, and import smoke tests
  for both `from agent_framework import <symbol>` and `from agent_framework import *`.

### Provider namespaces

Provider folders in core use `__getattr__` to lazy load from connector packages:

```python
# In agent_framework/foundry/__init__.py
_IMPORTS: dict[str, tuple[str, str]] = {
    "FoundryChatClient": ("agent_framework_foundry", "agent-framework-foundry"),
}

def __getattr__(name: str) -> Any:
    if name in _IMPORTS:
        import_path, package_name = _IMPORTS[name]
        try:
            return getattr(importlib.import_module(import_path), name)
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                f"The package {package_name} is required to use `{name}`. "
                f"Install it with: pip install {package_name}"
            ) from exc
```

## Adding a New Connector Package

**Important:** Do not create a new package unless approved by the core team.

Every new package starts as `alpha`.

### Alpha package checklist

1. Create directory under `packages/` (e.g., `packages/my-connector/`)
2. Add the package to `tool.uv.sources` in root `pyproject.toml`
3. Set the package version to the alpha pattern: `1.0.0a<date>`
4. Set the package classifier to `Development Status :: 3 - Alpha`
5. Include samples inside the package (e.g., `packages/my-connector/samples/`)
6. Do **NOT** add to `[all]` extra in `packages/core/pyproject.toml`
7. Do **NOT** create lazy loading in core yet
8. Add the package to `python/PACKAGE_STATUS.md` and keep that file updated when packages are added,
   removed, renamed, or promoted. If the package exposes individually staged APIs, keep the feature list
   there current too.

Recommended dependency workflow during connector implementation:

1. Add the dependency to the target package:
   `uv run poe add-dependency-to-project --package core --dependency "<dependency-spec>"`
2. Implement connector code and tests.
3. Validate dependency bounds for that package/dependency:
   `uv run poe validate-dependency-bounds-project --mode both --package core --dependency "<dependency-name>"`
4. If the package has meaningful tests/checks that validate dependency compatibility, you can use the add + validation flow in one command:
   `uv run poe add-dependency-and-validate-bounds --package core --dependency "<dependency-spec>"`
   If compatibility checks are not in place yet, add the dependency first, then implement tests before running bound validation.

### Promotion path

Promotion work is not isolated to the package being promoted. If a promotion changes dependency
metadata for downstream packages, also update the dependent packages' own versions so they publish
new metadata alongside the promoted dependency bounds.
Apply the internal package dependency update rules from the versioning section below during
promotions as well as standalone version update work.

#### Alpha -> Beta

Move a package to `beta` when it is stable enough to be part of the main install surface.

1. Update the package version to the beta pattern: `1.0.0b<date>`
2. Update the classifier to `Development Status :: 4 - Beta`
3. Add the package to `[all]` in `packages/core/pyproject.toml`
4. Move samples to the root `samples/` tree and remove package-local samples
5. Create or update the relevant lazy-loading namespace in core when the package belongs under one
6. Update `python/PACKAGE_STATUS.md`

After `alpha`, there should be no samples left inside a package folder.

#### Beta -> RC

Move a package to `rc` when its API is close to the final released shape.

1. Update the package version to the release-candidate pattern: `1.0.0rc<number>`
2. Keep the classifier at `Development Status :: 4 - Beta` because PyPI does not have a separate
   release-candidate classifier
3. Keep the package in `core[all]`
4. Keep samples only in the root `samples/` tree
5. Update `python/PACKAGE_STATUS.md` to show the package as `rc`

#### RC -> Released

Move a package to `released` when it no longer carries a prerelease qualifier.

1. Update the package version to the stable pattern: `1.0.0`
2. Update the classifier to `Development Status :: 5 - Production/Stable`
3. Keep the package in `core[all]`
4. Keep samples only in the root `samples/` tree
5. Update `python/PACKAGE_STATUS.md` to show the package as `released`
6. Update all `README.md` files that install that package with
   `pip install agent-framework-... --pre` so they use `pip install agent-framework-...` without
   the `--pre` suffix

## Versioning

### Internal package dependency updates

- If package A depends on package B within this repository, only update package A's dependency
  declaration when the work on package B actually affects package A.
- If package A does not need anything from the package B change, leave package A's dependency
  declaration unchanged.
- If package A does need something from the package B change, update package A's dependency
  declaration to the version or versioning scheme that matches what package A now requires.
- If package B is promoted to a different lifecycle stage, update package A's dependency
  declaration to the new versioning scheme for package B even when the only change is the stage
  transition itself.
- Use this guidance both for ordinary version updates and for package promotion work.

- All non-core packages declare a lower bound on `agent-framework-core`
- When core version bumps with breaking changes, update the lower bound in all packages
- Non-core packages version independently; only raise core bound when using new core APIs
- If promoting a package changes a dependent package's published dependency metadata, bump the
  dependent package's own version in the correct lifecycle pattern for its current stage
- Lifecycle version patterns:
  - `alpha`: `1.0.0a<date>` where `<date>` is the current Pacific (US west coast) `YYMMDD`
  - `beta`: `1.0.0b<date>` where `<date>` is the current Pacific (US west coast) `YYMMDD`
  - `rc`: `1.0.0rc<number>` where `<number>` increments only when the package has changes
  - `released`: `X.Y.Z` using semver per package
- For alpha/beta date stamps, use the current Pacific date as the cutoff, not UTC and not the user's local
  timezone. Same-Pacific-day re-cuts use a `.postN` suffix. Honor an explicit user-provided date over this
  default.
- Keep the `Development Status` classifier in `pyproject.toml` aligned with the lifecycle stage:
  - `alpha` -> `Development Status :: 3 - Alpha`
  - `beta` -> `Development Status :: 4 - Beta`
  - `rc` -> `Development Status :: 4 - Beta`
  - `released` -> `Development Status :: 5 - Production/Stable`
- See the PyPI classifier list for the available classifier values:
  `https://pypi.org/classifiers/`

## Installation Options

```bash
pip install agent-framework-core          # Core only
pip install agent-framework-core[all]     # Core + all connectors
pip install agent-framework               # Same as core[all]
pip install agent-framework-foundry       # Specific connector (pulls in core)
```

## Maintaining Documentation

When changing a package, check if its `AGENTS.md` needs updates:
- Adding/removing/renaming public classes or functions
- Changing the package's purpose or architecture
- Modifying import paths or usage patterns

Keep `python/PACKAGE_STATUS.md` updated when:
- A package is added, removed, renamed, or promoted between lifecycle stages
- A package starts or stops exposing individually staged experimental or release-candidate APIs

When a package adds, removes, or renames environment variables, update the related documentation in the same
change:
- The package's `README.md` for package-level configuration/env var guidance
- `samples/README.md` if the package is included in `packages/core/pyproject.toml` `[all]` and the env var is
  part of the consolidated package env-var inventory
- Any affected sample/package-local `.env.example`, `.env.template`, or sample README files when sample setup
  changes alongside the package
