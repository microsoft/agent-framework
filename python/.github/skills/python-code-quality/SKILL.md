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
#
# Division of labor (see "Type checking architecture" below):
#   - Pyright (strict) is the source-code type checker.
#   - Pyright (relaxed `basic`), mypy, pyrefly, ty, zuban all check the TESTS;
#     pyright/pyrefly/ty also check the SAMPLES (mypy/zuban skip script-style samples).
uv run poe pyright       # Pyright (strict) over SOURCE, fan-out across packages
uv run poe pyright -P core
uv run poe pyright -A
uv run poe test-typing   # mypy + pyrefly + ty + zuban + pyright over each package's TESTS
uv run poe test-typing -P core
uv run poe test-typing -S                       # samples (pyrefly + ty + pyright)
uv run poe test-typing -P core --checker mypy   # narrow to one checker (repeatable)
uv run poe test-typing -P core --checker pyright # relaxed pyright over the tests
uv run poe mypy          # alias: MyPy over the tests only
uv run poe mypy -P core
uv run poe typing        # Pyright (source) + the tests checkers
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

## Type checking architecture

Following the "too many type checkers" approach, type checkers are split by target:

| Target | Checker(s) | Mode | Config |
|--------|-----------|------|--------|
| Source (`agent_framework*`) | **pyright** | strict | `[tool.pyright]` in `pyproject.toml` |
| Tests | pyright, mypy, pyrefly, ty, zuban | relaxed/basic | `pyrightconfig.tests.json`, `[tool.mypy]`, `pyrefly.toml`, `ty` rules |
| Samples | pyright, pyrefly, ty | basic | `pyrightconfig.samples.json`, `pyrefly.samples.toml`, `ty.samples.toml` |

- **Pyright is the only *strict* source-code checker**, and it ALSO runs in a relaxed
  `basic` profile over the tests and samples (so the surfaces customers copy from are
  validated by every checker, including pyright). MyPy was removed from source; its
  `[tool.mypy]` block is now a *relaxed* profile used only for tests/samples.
- The extra checkers run over tests/samples because those exercise the public API the way
  users do. The profile is intentionally relaxed (private access allowed, untyped test
  bodies allowed) so authors aren't forced into ugly over-annotation.
- **Gating checkers** are `pyright`, `mypy`, `pyrefly`, `ty`, and `zuban` — all five run by
  default and gate CI. `zuban` is the strictest of the mypy-compatible pair, so the same
  `[tool.mypy]` config yields more findings; suppress zuban-only friction with shared
  `# type: ignore[code]`. Suppress relaxed-pyright friction with `# pyright: ignore[rule]`.
- **Samples** add `pyright` to `pyrefly` + `ty` — mypy/zuban can't resolve script-style
  sample layouts (numeric-prefixed dirs, duplicate `main.py`), but pyright handles them.
- The strict source-pyright (`[tool.pyright]`) enforces `reportUnnecessaryTypeIgnoreComment`
  and excludes tests/samples; the relaxed test/sample pyright configs do not flag unnecessary
  ignores.

## Ruff Configuration

- Line length: 120
- Target: Python 3.10+
- Auto-fix enabled
- Rules: ASYNC, B, CPY, D, E, ERA, F, FIX, I, INP, ISC, Q, RET, RSE, RUF, SIM, T20, TD, W, T100, S
- Scripts directory is excluded from checks

## Pyright Configuration

- **Source**: strict mode (`[tool.pyright]`), `reportUnnecessaryTypeIgnoreComment = "error"`,
  excludes tests, samples, .venv, packages/devui/frontend.
- **Tests**: relaxed `basic` profile (`pyrightconfig.tests.json`) — private import/usage and
  not-required TypedDict access allowed; runs as the `pyright` checker in `test-typing`.
- **Samples**: relaxed `basic` profile (`pyrightconfig.samples.json`, with a py310 variant) —
  runs as the `pyright` checker in `test-typing -S`.

## Parallel Execution

The task runner (`scripts/task_runner.py`) executes the cross-product of
(package × task) in parallel using ThreadPoolExecutor. Single items run
in-process with streaming output.

## CI Workflow

CI splits into 4 parallel jobs:
1. **Pre-commit hooks** — lightweight hooks (SKIP=poe-check)
2. **Package checks** — syntax/pyright (source) via check-packages
3. **Samples & markdown** — `check -S` plus `markdown-code-lint`
4. **Test Typing** — change-detected mypy/pyrefly/ty over tests (`ci-test-typing`)
