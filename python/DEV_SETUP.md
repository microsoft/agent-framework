# Dev Setup

This document describes how to setup your environment with Python and uv,
if you're working on new features or a bug fix for Agent Framework, or simply
want to run the tests included.

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


## Coding Standards

### Code Style and Formatting

We use [ruff](https://github.com/astral-sh/ruff) for both linting and formatting with the following configuration:

- **Line length**: 120 characters
- **Target Python version**: 3.10+
- **Google-style docstrings**: All public functions, classes, and modules should have docstrings following Google conventions

### Function Parameter Guidelines

To make the code easier to use and maintain:

- **Positional parameters**: Only use for up to 3 fully expected parameters
- **Keyword parameters**: Use for all other parameters, especially when there are multiple required parameters without obvious ordering
- **Avoid additional imports**: Do not require the user to import additional modules to use the function, so provide string based overrides when applicable, for instance:
```python
def create_agent(name: str, tool_mode: ChatToolMode) -> Agent:
    # Implementation here
```
Should be:
```python
def create_agent(name: str, tool_mode: Literal['auto', 'required', 'none'] | ChatToolMode) -> Agent:
    # Implementation here
    if isinstance(tool_mode, str):
        tool_mode = ChatToolMode(tool_mode)
```
- **Document kwargs**: Always document how `kwargs` are used, either by referencing external documentation or explaining their purpose
- **Separate kwargs**: When combining kwargs for multiple purposes, use specific parameters like `client_kwargs: dict[str, Any]` instead of mixing everything in `**kwargs`

Example:
```python
chat_completion = OpenAIChatClient(env_file_path="openai.env")
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

## Implementation Decisions

### Asynchronous programming

It's important to note that most of this library is written with asynchronous in mind. The
developer should always assume everything is asynchronous. One can use the function signature
with either `async def` or `def` to understand if something is asynchronous or not.

### Documentation

Each file should have a single first line containing: # Copyright (c) Microsoft. All rights reserved.

We follow the [Google Docstring](https://github.com/google/styleguide/blob/gh-pages/pyguide.md#383-functions-and-methods) style guide for functions and methods.
They are currently not checked for private functions (functions starting with '_').

They should contain:

- Single line explaining what the function does, ending with a period.
- If necessary to further explain the logic a newline follows the first line and then the explanation is given.
- The following three sections are optional, and if used should be separated by a single empty line.
- Arguments are then specified after a header called `Args:`, with each argument being specified in the following format:
  - `arg_name`: Explanation of the argument.
    - if a longer explanation is needed for a argument, it should be placed on the next line, indented by 4 spaces.
    - Type and default values do not have to be specified, they will be pulled from the definition.
- Returns are specified after a header called `Returns:` or `Yields:`, with the return type and explanation of the return value.
- Finally, a header for exceptions can be added, called `Raises:`, with each exception being specified in the following format:
  - `ExceptionType`: Explanation of the exception.
  - if a longer explanation is needed for a exception, it should be placed on the next line, indented by 4 spaces.

Putting them all together, gives you at minimum this:

```python
def equal(arg1: str, arg2: str) -> bool:
    """Compares two strings and returns True if they are the same."""
    ...
```

Or a complete version of this:

```python
def equal(arg1: str, arg2: str) -> bool:
    """Compares two strings and returns True if they are the same.

    Here is extra explanation of the logic involved.

    Args:
        arg1: The first string to compare.
        arg2: The second string to compare.

    Returns:
        True if the strings are the same, False otherwise.
    """
```

### Attributes vs Inheritance

Prefer attributes over inheritance when parameters are mostly the same:

```python
# ✅ Preferred - using attributes
from agent_framework import ChatMessage

user_msg = ChatMessage(role="user", content="Hello, world!")
asst_msg = ChatMessage(role="assistant", content="Hello, world!")

# ❌ Not preferred - unnecessary inheritance
from agent_framework import UserMessage, AssistantMessage

user_msg = UserMessage(content="Hello, world!")
asst_msg = AssistantMessage(content="Hello, world!")
```

### Logging

Use the centralized logging system:

```python
from agent_framework import get_logger

# For main package
logger = get_logger()

# For subpackages
logger = get_logger('agent_framework.azure')
```

**Do not use** direct logging module imports:
```python
# ❌ Avoid this
import logging
logger = logging.getLogger(__name__)
```

### Import Structure

The package follows a flat import structure:

- **Core**: Import directly from `agent_framework`
  ```python
  from agent_framework import ChatAgent, ai_function
  ```

- **Components**: Import from `agent_framework.<component>`
  ```python
  from agent_framework.vector_data import VectorStoreModel
  from agent_framework.guardrails import ContentFilter
  ```

- **Connectors**: Import from `agent_framework.<vendor/platform>`
  ```python
  from agent_framework.openai import OpenAIChatClient
  from agent_framework.azure import AzureOpenAIChatClient
  ```

## Testing

### Running Tests

```bash
# Run all tests with coverage
uv run poe test

# Run specific test file
uv run pytest tests/test_agents.py

# Run with verbose output
uv run pytest -v
```

### Test Coverage

- Target: Minimum 80% test coverage for all packages
- Coverage reports are generated automatically during test runs
- Tests should be in corresponding `test_*.py` files in the `tests/` directory

## Documentation

### Building Documentation

```bash
# Build documentation
uv run poe docs-build

# Serve documentation locally with auto-reload
uv run poe docs-serve

# Check documentation for warnings
uv run poe docs-check
```

### Docstring Style

Use Google-style docstrings for all public APIs:

```python
def create_agent(name: str, chat_client: ChatClientProtocol) -> Agent:
    """Create a new agent with the specified configuration.

    Args:
        name: The name of the agent.
        chat_client: The chat client to use for communication.

    Returns:
        True if the strings are the same, False otherwise.

    Raises:
        ValueError: If one of the strings is empty.
    """
    ...
```

If in doubt, use the link above to read much more considerations of what to do and when, or use common sense.

## Coding standards

```plaintext
agent_framework/
├── __init__.py              # Tier 0: Core components
├── _agents.py              # Agent implementations
├── _tools.py               # Tool definitions
├── _models.py              # Type definitions
├── _logging.py             # Logging utilities
├── context_providers.py    # Tier 1: Context providers
├── guardrails.py          # Tier 1: Guardrails and filters
├── vector_data.py         # Tier 1: Vector stores
├── workflows.py           # Tier 1: Multi-agent orchestration
└── azure/                 # Tier 2: Azure connectors (lazy loaded)
    └── __init__.py        # Imports from agent-framework-azure
```

### Pydantic and Serialization

This section describes how one can enable serialization for their class using Pydantic.
For more info you can refer to the [Pydantic Documentation](https://docs.pydantic.dev/latest/).

#### Upgrading existing classes to use Pydantic

Let's take the following example:

```python
class A:
    def __init__(self, a: int, b: float, c: List[float], d: dict[str, tuple[float, str]] = {}):
        self.a = a
        self.b = b
        self.c = c
        self.d = d
```

You would convert this to a Pydantic class by sub-classing from the `AFBaseModel` class.

```python
from pydantic import Field
from ._pydantic import AFBaseModel

class A(AFBaseModel):
    # The notation for the fields is similar to dataclasses.
    a: int
    b: float
    c: list[float]
    # Only, instead of using dataclasses.field, you would use pydantic.Field
    d: dict[str, tuple[float, str]] = Field(default_factory=dict)
```

#### Classes with data that need to be serialized, and some of them are Generic types

Let's take the following example:

```python
from typing import TypeVar

T1 = TypeVar("T1")
T2 = TypeVar("T2", bound=<some class>)

class A:
    def __init__(a: int, b: T1, c: T2):
        self.a = a
        self.b = b
        self.c = c
```

You can use the `AFBaseModel` to convert these to pydantic serializable classes.

```python
from typing import Generic, TypeVar

from ._pydantic import AFBaseModel

T1 = TypeVar("T1")
T2 = TypeVar("T2", bound=<some class>)

class A(AFBaseModel, Generic[T1, T2]):
    # T1 and T2 must be specified in the Generic argument otherwise, pydantic will
    # NOT be able to serialize this class
    a: int
    b: T1
    c: T2
```

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

#### `docs-install`
Install including the documentation tools:
```bash
uv run poe docs-install
```

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

#### `docs-full`
Build the packages, clean and build the documentation:
```bash
uv run poe docs-full
```

#### `docs-rebuild`
Clean and build the documentation:
```bash
uv run poe docs-rebuild
```

#### `docs-full-install`
Install the docs dependencies, build the packages, clean and build the documentation:
```bash
uv run poe docs-full-install
```

#### `docs-debug`
Build the documentation with debug information:
```bash
uv run poe docs-debug
```

#### `docs-rebuild-debug`
Clean and build the documentation with debug information:
```bash
uv run poe docs-rebuild-debug
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
