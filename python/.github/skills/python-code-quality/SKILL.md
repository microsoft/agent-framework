---
name: python-code-quality
description: >
  Code quality checks, linting, formatting, and type checking commands for the
  Agent Framework Python codebase. Use this when running checks, fixing lint
  errors, or troubleshooting CI failures.
---

# Python Code Quality

## Quick Commands

All commands run from the `python/` directory:

```bash
# Syntax formatting + checks (parallel across packages by default)
uv run poe syntax
uv run poe syntax -P core
uv run poe syntax -F    # Format only
uv run poe syntax -C    # Check only
uv run poe syntax -S    # Samples only

# Type checking
uv run poe pyright       # Pyright fan-out across packages
uv run poe pyright -P core
uv run poe pyright -A
uv run poe mypy          # MyPy fan-out across packages
uv run poe mypy -P core
uv run poe mypy -A
uv run poe typing        # Both pyright and mypy
uv run poe typing -P core
uv run poe typing -A

# All package-level checks in parallel (syntax + pyright)
uv run poe check-packages

# Full check (packages + samples + tests + markdown)
uv run poe check
uv run poe check -P core

# Samples only
uv run poe check -S
uv run poe pyright -S

# Markdown code blocks
uv run poe markdown-code-lint
```

## Pre-commit Hooks (prek)

Prek hooks run automatically on commit. They stay lightweight and only check
changed files.

```bash
# Install hooks
uv run poe prek-install

# Run all hooks manually
uv run prek run -a

# Run on last commit
uv run prek run --last-commit
```

They run changed-package syntax formatting/checking, markdown code lint only
when markdown files change, and sample syntax lint/pyright only when files
under `samples/` change.
They intentionally do not run workspace `pyright` or `mypy` by default.

## Ruff Configuration

- Line length: 120
- Target: Python 3.10+
- Auto-fix enabled
- Rules: ASYNC, B, CPY, D, E, ERA, F, FIX, I, INP, ISC, Q, RET, RSE, RUF, SIM, T20, TD, W, T100, S
- Scripts directory is excluded from checks

## Pyright Configuration

- Strict mode enabled
- Excludes: tests, .venv, packages/devui/frontend

## Parallel Execution

The task runner (`scripts/task_runner.py`) executes the cross-product of
(package × task) in parallel using ThreadPoolExecutor. Single items run
in-process with streaming output.

## CI Workflow

CI splits into 4 parallel jobs:
1. **Pre-commit hooks** — lightweight hooks (SKIP=poe-check)
2. **Package checks** — syntax/pyright via check-packages
3. **Samples & markdown** — `check -S` plus `markdown-code-lint`
4. **Mypy** — change-detected mypy checks
