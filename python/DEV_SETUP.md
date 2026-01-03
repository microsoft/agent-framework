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
# Install pre-commit hooks
uv run poe pre-commit-install
```

Alternatively, you can reinstall the venv, pacakges, dependencies and pre-commit hooks with a single command (but this requires poe in the current env), this is especially useful if you want to switch python versions:

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

chat_client = OpenAIChatClient(env_file_path="openai.env")
```

## Tests

All the tests are located in the `tests` folder of each package. There are tests that are marked with a `@skip_if_..._integration_tests_disabled` decorator, these are integration tests that require an external service to be running, like OpenAI or Azure OpenAI.

If you want to run these tests, you need to set the environment variable `RUN_INTEGRATION_TESTS` to `true` and have the appropriate key per services set in your environment or in a `.env` file.

Alternatively, you can run them using VSCode Tasks. Open the command palette
(`Ctrl+Shift+P`) and type `Tasks: Run Task`. Select `Test` from the list.

If you want to run the tests for a single package, you can use the `uv run poe test` command with the package name as an argument. For example, to run the tests for the `agent_framework` package, you can use:

```bash
uv run poe --directory packages/core test
```

These commands also output the coverage report.

## Code quality checks

To run the same checks that run during a commit and the GitHub Action `Python Code Quality`, you can use this command, from the [python](../python) folder:

```bash
    uv run poe check
```

Ideally you should run these checks before committing any changes, when you install using the instructions above the pre-commit hooks should be installed already.

## Code Coverage

We try to maintain a high code coverage for the project. To run the code coverage on the unit tests, you can use the following command:

```bash
    uv run poe test
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

After this initial setup, you can use the following tasks to manage your development environment. It is advised to use the following setup command since that also installs the pre-commit hooks.

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

### Code Validation

#### `markdown-code-lint`
Lint markdown code blocks:
```bash
uv run poe markdown-code-lint
```

### Comprehensive Checks

#### `check`
Run all quality checks (format, lint, pyright, mypy, test, markdown lint):
```bash
uv run poe check
```

### Testing

#### `test`
Run unit tests with coverage by invoking the `test` task in each package sequentially:
```bash
uv run poe test
```

To run tests for a specific package only, use the `--directory` flag:
```bash
# Run tests for the core package
uv run --directory packages/core poe test

# Run tests for the azure-ai package
uv run --directory packages/azure-ai poe test
```

#### `all-tests`
Run all tests in a single pytest invocation across all packages in parallel (excluding lab and devui). This is faster than `test` as it uses pytest's parallel execution:
```bash
uv run poe all-tests
```

#### `all-tests-cov`
Same as `all-tests` but with coverage reporting enabled:
```bash
uv run poe all-tests-cov
```

### Building and Publishing

#### `build`
Build all packages:
```bash
uv run poe build
```

#### `clean-dist`
Clean the dist directories:
```bash
uv run poe clean-dist
```

#### `publish`
Publish packages to PyPI:
```bash
uv run poe publish
```

## Pre-commit Hooks

Pre-commit hooks run automatically on commit and execute a subset of the checks on changed files only. You can also run all checks using pre-commit directly:

```bash
uv run pre-commit run -a
```
