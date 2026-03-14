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
# Format code (ruff format, parallel across packages)
uv run poe fmt

# Lint and auto-fix (ruff check, parallel across packages)
uv run poe lint

# Type checking
uv run poe pyright       # Pyright (parallel across packages)
uv run poe mypy          # MyPy (parallel across packages)
uv run poe typing        # Both pyright and mypy

# All package-level checks in parallel (fmt + lint + pyright + mypy)
uv run poe check-packages

# Full check (packages + samples + tests + markdown)
uv run poe check

# Samples only
uv run poe samples-lint     # Ruff lint on samples/
uv run poe samples-syntax   # Pyright syntax check on samples/

# Markdown code blocks
uv run poe markdown-code-lint
```

## Pre-commit Hooks (prek)

Prek hooks run automatically on commit. They check only changed files and run
package-level checks in parallel for affected packages only.

```bash
# Install hooks
uv run poe prek-install

# Run all hooks manually
uv run prek run -a

# Run on last commit
uv run prek run --last-commit
```

When core package changes, type-checking (mypy, pyright) runs across all packages
since type changes propagate. Format and lint only run in changed packages.

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
2. **Package checks** — fmt/lint/pyright via check-packages
3. **Samples & markdown** — samples-lint, samples-syntax, markdown-code-lint
4. **Mypy** — change-detected mypy checks
