# Python

This project uses [poethepoet](https://github.com/nat-n/poethepoet) for task management and [uv](https://github.com/astral-sh/uv) for dependency management.

## Available Poe Tasks

### Setup and Installation

Once uv is installed, and you do not yet have a virtual environment setup:

```bash
uv venv
```

and then you can run the following tasks:
```bash
uv sync --all-extras --dev
```

After this initial setup, you can use the following tasks to manage your development environment, it is adviced to use the following setup command since that also installs the pre-commit hooks.

#### `setup`
Set up the development environment with a virtual environment, install dependencies and pre-commit hooks:
```bash
uv run poe setup
# or with specific Python version
uv run poe setup --python 3.12
```

#### `install`
Install all dependencies including extras and dev dependencies, including updates:
```bash
uv run poe install
```

#### `venv`
Create a virtual environment with specified Python version or switch python version:
```bash
uv run poe venv
# or with specific Python version
uv run poe venv --python 3.12
```

#### `pre-commit-install`
Install pre-commit hooks:
```bash
uv run poe pre-commit-install
```

### Code Quality and Formatting

Each of the following tasks are designed to run against both the main `agent-framework` package and the extension packages, ensuring consistent code quality across the project.

#### `fmt` (format)
Format code using ruff:
```bash
uv run poe fmt
```

#### `lint`
Run linting checks and fix issues:
```bash
uv run poe lint
```

#### `pyright`
Run Pyright type checking:
```bash
uv run poe pyright
```

#### `mypy`
Run MyPy type checking:
```bash
uv run poe mypy
```

### Testing

#### `test`
Run unit tests with coverage:
```bash
uv run poe test
```

### Documentation

#### `docs-clean`
Remove the docs build directory:
```bash
uv run poe docs-clean
```

#### `docs-build`
Build the documentation:
```bash
uv run poe docs-build
```

#### `docs-serve`
Serve documentation locally with auto-reload:
```bash
uv run poe docs-serve
```

#### `docs-check`
Build documentation and fail on warnings:
```bash
uv run poe docs-check
```

#### `docs-check-examples`
Check documentation examples for code correctness:
```bash
uv run poe docs-check-examples
```

### Code Validation

#### `markdown-code-lint`
Lint markdown code blocks:
```bash
uv run poe markdown-code-lint
```

#### `samples-code-check`
Run type checking on samples:
```bash
uv run poe samples-code-check
```

### Comprehensive Checks

#### `check`
Run all quality checks (format, lint, pyright, mypy, test, markdown lint, samples check):
```bash
uv run poe check
```

#### `pre-commit-check`
Run pre-commit specific checks (all of the above, excluding `mypy`):
```bash
uv run poe pre-commit-check
```

### Building

#### `build`
Build the package:
```bash
uv run poe build
```

## Pre-commit Hooks

You can also run all checks using pre-commit directly:

```bash
uv run pre-commit run -a
```
