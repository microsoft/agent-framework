# Dev Setup

This document describes how to setup your environment with Python and uv,
if you're working on new features or a bug fix for Agent Framework, or simply
want to run the tests included.

For coding standards and conventions, see [CODING_STANDARD.md](CODING_STANDARD.md).

## System setup

We are using a tool called [poethepoet](https://github.com/nat-n/poethepoet) for task management and [uv](https://github.com/astral-sh/uv) for dependency management. At the [end of this document](#available-poe-tasks), you will find the available Poe tasks.

## If you're on WSL

Check that you've cloned the repository to `~/workspace` or a similar folder.
Avoid `/mnt/c/` and prefer using your WSL user's home directory.

Ensure you have the WSL extension for VSCode installed.

## Using uv

uv allows us to use AF from the local files, without worrying about paths, as
if you had AF pip package installed.

To install AF and all the required tools in your system, first, navigate to the directory containing
this DEV_SETUP using your chosen shell.

### For windows (non-WSL)

Check the [uv documentation](https://docs.astral.sh/uv/getting-started/installation/) for the installation instructions. At the time of writing this is the command to install uv:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### For WSL, Linux or MacOS

Check the [uv documentation](https://docs.astral.sh/uv/getting-started/installation/) for the installation instructions. At the time of writing this is the command to install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Alternative for MacOS

For MacOS users, Homebrew provides an easy installation of uv with the [uv Formulae](https://formulae.brew.sh/formula/uv)

```bash
brew install uv
```


### After installing uv

You can then run the following commands manually:

```bash
# Install Python 3.10, 3.11, 3.12, and 3.13
uv python install 3.10 3.11 3.12 3.13
# Create a virtual environment with Python 3.10 (you can change this to 3.11, 3.12 or 3.13)
$PYTHON_VERSION = "3.10"
uv venv --python $PYTHON_VERSION
# Install AF and all dependencies
uv sync --dev
# Install all the tools and dependencies
uv run poe install
# Install prek hooks
uv run poe prek-install
```

Alternatively, you can reinstall the venv, pacakges, dependencies and prek hooks with a single command (but this requires poe in the current env), this is especially useful if you want to switch python versions:

```bash
uv run poe setup -p 3.13
```

You can then run different commands through Poe the Poet, use `uv run poe` to discover which ones.

## VSCode Setup

Install the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python) for VSCode.

Open the `python` folder in [VSCode](https://code.visualstudio.com/docs/editor/workspaces).
> The workspace for python should be rooted in the `./python` folder.

Open any of the `.py` files in the project and run the `Python: Select Interpreter`
command from the command palette. Make sure the virtual env (default path is `.venv`) created by `uv` is selected.

## LLM setup

Make sure you have an
[OpenAI API Key](https://platform.openai.com) or
[Azure OpenAI service key](https://learn.microsoft.com/azure/cognitive-services/openai/quickstart?pivots=rest-api)

There are two methods to manage keys, secrets, and endpoints:

1. Store them in environment variables. AF Python leverages pydantic settings to load keys, secrets, and endpoints from the environment.
    > When you are using VSCode and have the python extension setup, it automatically loads environment variables from a `.env` file, so you don't have to manually set them in the terminal.
    > During runtime on different platforms, environment settings set as part of the deployments should be used.

2. Store them in a separate `.env` file, like `dev.env`, you can then pass that name into the constructor for most services, to the `env_file_path` parameter, see below.
    > Make sure to add `*.env` to your `.gitignore` file.

### Example for file-based setup with OpenAI Chat Completions
To configure a `.env` file with just the keys needed for OpenAI Chat Completions, you can create a `openai.env` (this name is just as an example, a single `.env` with all required keys is more common) file in the root of the `python` folder with the following content:

Content of `.env` or `openai.env`:

```env
OPENAI_API_KEY=""
OPENAI_CHAT_MODEL_ID="gpt-4o-mini"
```

You will then configure the ChatClient class with the keyword argument `env_file_path`:

```python
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(env_file_path="openai.env")
```

## Tests

All the tests are located in the `tests` folder of each package. Tests marked with `@pytest.mark.integration` and `@skip_if_..._integration_tests_disabled` are integration tests that require external services (e.g., OpenAI, Azure OpenAI). They are automatically skipped when the required API keys or service endpoints are not configured in your environment or `.env` file.

The root `test` command now supports both project-scoped fan-out and a single aggregate sweep:

```bash
# Run package-local tests across all workspace packages
uv run poe test

# Run tests for one workspace package
uv run poe test -P core

# Run an aggregate pytest sweep across the selected packages
uv run poe test -A

# Run only unit tests in aggregate mode
uv run poe test -A -m "not integration"

# Run only integration tests in aggregate mode
uv run poe test -A -m integration

# Run tests with coverage for one package or an aggregate sweep
uv run poe test -P core -C
uv run poe test -A -C
```

Alternatively, you can run them using VSCode Tasks. Open the command palette
(`Ctrl+Shift+P`) and type `Tasks: Run Task`. Select `Test` from the list.

Direct package execution still works when you need it:

```bash
uv run poe --directory packages/core test
```

Large packages (core, ag-ui, orchestrations, anthropic) use `pytest-xdist` for parallel test execution within the package. The aggregate `test -A` sweep also uses `pytest-xdist` across the selected packages.

## Code quality checks

To run the same checks that run during a commit and the GitHub Action `Python Code Quality`, you can use this command, from the [python](../python) folder:

```bash
    uv run poe check
```

Ideally you should run these checks before committing any changes, when you install using the instructions above the prek hooks should be installed already.

## Code Coverage

We try to maintain a high code coverage for the project. To review coverage locally, use either a package-scoped run or the aggregate sweep:

```bash
uv run poe test -P core -C
uv run poe test -A -C
```

This will show you which files are not covered by the tests, including the specific lines not covered. Make sure to consider the untested lines from the code you are working on, but feel free to add other tests as well, that is always welcome!

## Catching up with the latest changes

There are many people committing to Semantic Kernel, so it is important to keep your local repository up to date. To do this, you can run the following commands:

```bash
    git fetch upstream main
    git rebase upstream/main
    git push --force-with-lease
```

or:

```bash
    git fetch upstream main
    git merge upstream/main
    git push
```

This is assuming the upstream branch refers to the main repository. If you have a different name for the upstream branch, you can replace `upstream` with the name of your upstream branch.

After running the rebase command, you may need to resolve any conflicts that arise. If you are unsure how to resolve a conflict, please refer to the [GitHub's documentation on resolving conflicts](https://docs.github.com/en/get-started/using-git/resolving-merge-conflicts-after-a-git-rebase), or for [VSCode](https://code.visualstudio.com/docs/sourcecontrol/overview#_merge-conflicts).

# Task automation

## Available Poe Tasks
This project uses [poethepoet](https://github.com/nat-n/poethepoet) for task management and [uv](https://github.com/astral-sh/uv) for dependency management.

### Setup and Installation

Once uv is installed, and you do not yet have a virtual environment setup:

```bash
uv venv
```

and then you can run the following tasks:
```bash
uv sync --all-extras --dev
```

After this initial setup, you can use the following tasks to manage your development environment. It is advised to use the following setup command since that also installs the prek hooks.

#### `setup`
Set up the development environment with a virtual environment, install dependencies and prek hooks:
```bash
uv run poe setup
# or with specific Python version
uv run poe setup -P 3.12
```

#### `install`
Install all dependencies (including extras and dev dependencies) from the lockfile using frozen resolution:
```bash
uv run poe install
```
For intentional dependency upgrades, run `uv lock --upgrade-package <dependency-name>` and then run `uv run poe install`.

For repo-wide dev tooling refreshes, run `uv run poe upgrade-dev-dependencies` to repin dev dependencies, refresh `uv.lock`, and rerun validation, typing, and tests.

#### `venv`
Create a virtual environment with specified Python version or switch python version:
```bash
uv run poe venv
# or with specific Python version
uv run poe venv -P 3.12
```

#### `prek-install`
Install prek hooks:
```bash
uv run poe prek-install
```

### Project-scoped command families

These commands default to `--package "*"`, so they run across all workspace packages unless you narrow them with `-P/--package`:

#### `syntax`
Run Ruff formatting plus Ruff lint checks by default:
```bash
uv run poe syntax
uv run poe syntax -P core
uv run poe syntax -F        # format only
uv run poe syntax -C        # lint/check only
```

#### `build`
Build workspace packages and the root meta package:
```bash
uv run poe build
uv run poe build -P core
```

#### `clean-dist`
Clean generated dist artifacts:
```bash
uv run poe clean-dist
uv run poe clean-dist -P core
```

### Dual-mode validation and test commands

These command families share the same selector model:

```bash
uv run poe <command>              # project fan-out over --package "*"
uv run poe <command> -P core      # one-project fan-out
uv run poe <command> -A           # aggregate sweep where supported
```

#### `pyright`
Run Pyright type checking:
```bash
uv run poe pyright
uv run poe pyright -P core
uv run poe pyright -A
```

#### `mypy`
Run MyPy type checking:
```bash
uv run poe mypy
uv run poe mypy -P core
uv run poe mypy -A
```

#### `typing`
Run both Pyright and MyPy:
```bash
uv run poe typing
uv run poe typing -P core
uv run poe typing -A
```

#### `test`
Run package-local tests in fan-out mode, or switch to one aggregate pytest sweep with `-A`:
```bash
uv run poe test
uv run poe test -P core
uv run poe test -P core -C
uv run poe test -A
uv run poe test -A -C
```

### Sample-target variants

Use `-S/--samples` for sample-only validation instead of separate top-level commands:

```bash
uv run poe syntax -S
uv run poe syntax -S -C
uv run poe pyright -S
uv run poe check -S
```

### Workspace validation and dependency commands

#### `markdown-code-lint`
Lint markdown code blocks:
```bash
uv run poe markdown-code-lint
```

#### `check-packages`
Run the package-level syntax sweep (`syntax`) plus `pyright` across the selected projects:
```bash
uv run poe check-packages
uv run poe check-packages -P core
```

#### `check`
Run package syntax, pyright, and tests for the selected project set. Without `-P/--package`, it also includes sample checks and markdown lint:
```bash
uv run poe check
uv run poe check -P core
uv run poe check -S
```

#### `validate-dependency-bounds-test`
Run workspace-wide dependency compatibility gates at lower and upper resolutions. This runs test + pyright across all packages and stops on first failure:
```bash
uv run poe validate-dependency-bounds-test
# Defaults to --package "*"; pass a package to scope test mode
uv run poe validate-dependency-bounds-test -P core
```

#### `validate-dependency-bounds-project`
Validate and extend dependency bounds for a single dependency in a single package. Use `--mode lower`, `--mode upper`, or the default `--mode both`:
```bash
uv run poe validate-dependency-bounds-project -M both -P core -D "<dependency-name>"
```
`--package` defaults to `*`, and `--dependency` is optional. Automation can use `--mode upper --package "*"` to run the upper-bound pass across the workspace.
For `<1.0` dependencies, prefer the broadest validated range the package can really support. That may still be a single patch or minor line, but multi-minor ranges are fine when the package's checks/tests prove they work.

#### `add-dependency-and-validate-bounds`
Add an external dependency to a workspace project and run both validators for that same project/dependency:
```bash
uv run poe add-dependency-and-validate-bounds -P core -D "<dependency-spec>"
```

#### `upgrade-dev-dependencies`
Refresh exact dev dependency pins across the workspace, run `uv lock --upgrade`, reinstall from the frozen lockfile, then rerun validation, typing, and tests:
```bash
uv run poe upgrade-dev-dependencies
```
Use this for repo-wide dev tooling refreshes. For targeted runtime dependency upgrades, prefer `uv lock --upgrade-package <dependency-name>` plus the package-scoped bound validation tasks above.

### Building and Publishing

#### `publish`
Publish packages to PyPI:
```bash
uv run poe publish
```

### Compatibility aliases

These legacy commands still work during the transition, but prefer the newer forms above:

```bash
uv run poe fmt             # prefer: uv run poe syntax -F
uv run poe format          # prefer: uv run poe syntax -F
uv run poe lint            # prefer: uv run poe syntax -C
uv run poe all-tests       # prefer: uv run poe test -A
uv run poe all-tests-cov   # prefer: uv run poe test -A -C
uv run poe samples-lint    # prefer: uv run poe syntax -S -C
uv run poe samples-syntax  # prefer: uv run poe pyright -S
```

## Prek Hooks

Prek hooks run automatically on commit and stay intentionally lightweight:

- changed-package syntax formatting
- changed-package syntax lint/check
- markdown code lint only when markdown files change
- sample lint + sample pyright only when files under `samples/` change

They do **not** run workspace `pyright` or `mypy` by default. Use `uv run poe pyright`, `uv run poe mypy`, `uv run poe typing`, `uv run poe check-packages`, or `uv run poe check` when you want deeper validation.

You can run the installed hooks directly with:

```bash
uv run prek run -a
```
