# Python Package design for Agent Framework

## Design goals
* Developer experience is key
    * the components needed for a basic agent with tools and a runtime should be importable from `agent_framework` without having to import from subpackages. This will be referred to as _tier 0_ components.
    * for more advanced components, _tier 1_ components, such as context providers, guardrails, vector data, text search, exceptions, evaluation, utils, telemetry and workflows, they should be importable from `agent_framework.<component>`, so for instance `from agent_framework.vector_data import vectorstoremodel`.
    * for parts of the package that are either additional functionality or integrations with other services (connectors) (_tier 2_), we use the term _tier 2_, however they should also be importable from `agent_framework.<component>`, so for instance `from agent_framework.openai import OpenAIClient`.
        * this means that the package structure is flat, and the components are grouped by functionality, not by type, so for instance `from agent_framework.openai import OpenAIChatClient` will import the OpenAI chat client, but also the OpenAI tools, and any other OpenAI related functionality.
        * There should not be a need for deeper imports from those packages, unless a good case is made for that, so the internals of the extensions packages should always be a folder with the name of the package, a `__init__.py` and one or more `_files.py` file, where the `_files.py` file contains the implementation details, and the `__init__.py` file exposes the public interface.
    * if a single file becomes too cumbersome (files are allowed to be 1k+ lines) it should be split into a folder with an `__init__.py` that exposes the public interface and a `_files.py` that contains the implementation details, with a `__all__` in the init to expose the right things, if there are very large dependencies being loaded it can optionally using lazy loading to avoid loading the entire package when importing a single component.
    * as much as possible, related things are in a single file which makes understanding the code easier.
    * simple and straightforward logging and telemetry setup, so developers can easily add logging and telemetry to their code without having to worry about the details.
* Independence of connectors
    * To allow connectors to be treated as independent packages, we will use namespace packages for connectors, in principle this only includes the packages that we will develop in our repo, since that is easy to manage and maintain.
    * further advantages are that each package can have a independent lifecycle, versioning, and dependencies.
    * and this gives us insights into the usage, through pip install statistics, especially for connectors to services outside of Microsoft.
    * the goal is to group related connectors based on vendors, not on types, so for instance doing: `import agent_framework.google` will import connectors for all Google services, such as `GoogleChatClient` but also `BigQueryCollection`, etc.
    * All dependencies for a subpackage should be required dependencies in that package, and that package becomes a optional dependency in the main package as an _extra_ with the same name, so in the main `pyproject.toml` we will have:
        ```toml
        [project.optional-dependencies]
        google = [
            "agent-framework-google == 1.0.0"
        ]
        ```
    * this means developers can use `pip install agent-framework[google]` to get AF with all Google connectors and dependencies, as well as manually installing the subpackage with `pip install agent-framework-google`.

### Sample getting started code
```python
from typing import Annotated
from agent_framework import Agent, ai_function
from agent_framework.openai import OpenAIChatClient

@ai_function(description="Get the current weather in a given location")
async def get_weather(location: Annotated[str, "The location as a city name"]) -> str:
    """Get the current weather in a given location."""
    # Implementation of the tool to get weather
    return f"The current weather in {location} is sunny."

agent = Agent(
    name="MyAgent",
    model_client=OpenAIChatClient(),
    tools=get_weather,
    description="An agent that can get the current weather.",
)
response = await agent.run("What is the weather in Amsterdam?")
print(response)
```

## Global Package structure
Overall the following structure is proposed:

* agent-framework
    * core components, will be exposed directly from `agent_framework`:
        * (single) agents (includes threads)
        * tools (includes MCP and OpenAPI)
        * models/types (name tbd, will include the equivalent of MEAI for dotnet; content types and client abstractions)
        * logging
    * advanced components, will be exposed from `agent_framework.<component>`:
        * context_providers (tbd)
        * guardrails / filters
        * vector_data (vector stores and other MEVD pieces)
        * text_search
        * exceptions
        * evaluations
        * utils (optional)
        * telemetry (could also be observability or monitoring)
        * workflows (includes multi-agent orchestration)
    * connectors; subpackages
        * Subpackages are any additional functionality that is useful for a user, to reduce friction they will imported in a similar way as advanced components, however the code for them will be in a separate package, so that they can be installed separately, they must expose all public items, in their main `__init__.py` file, so that they can be imported from the main package without additional import levels.
        In the main package a corresponding folder will be created, with a `__init__.py` file that lazy imports the public items from the subpackage, so that they can be exposed from the main package.
        * Some examples are:
            * azure (non LLM integrations)
            * will be exposed through i.e. `agent_framework.azure`
            * anything other then a connector that we want to expose as a separate package, for instance:
                * mem0 (memory management)
                * would be exposed through i.e. `agent_framework.mem0`
        * A package name cannot overlap with each other or with components in the main package, so `guardrails` cannot be used as a package name, since it is already used in the main package.
            * A package can implement additional guardrails functionality, but that would become something like `from agent_framework.azure import ContentSafetyGuardrail`, which would contain a guardrail implementation using Azure Content Safety, but it is not the same as the `agent_framework.guardrails` component.
* tests
* samples
* extensions
    * azure
    * ...

All the init's will use lazy loading so avoid importing the entire package when importing a single component.
Internal imports will be done using relative imports, so that the package can be used as a namespace package.

### File structure
The resulting file structure will be as follows:

```plaintext
packages/
    main/
        agent_framework/
            openai/
                __init__.py
                _chat_client.py
                _shared.py
                exceptions.py
            __init__.py
            __init__.pyi
            _agents.py
            _tools.py
            _models.py
            _logging.py
            context_providers.py
            guardrails.py
            exceptions.py
            evaluations.py
            utils.py
            telemetry.py
            templates.py
            text_search.py
            vector_data.py
            workflows.py
            py.typed
        tests/
            unit/
                test_types.py
            integration/
                test_chat_clients.py
        pyproject.toml
        README.md
        ...
    mem0/
        agent_framework/
            mem0/
                __init__.py
                _mem0.py
                ...
    redis/
        ...
    google/
        agent_framework/
            google/
                __init__.py
                _chat.py
                _bigquery.py
                ...
        tests/
            unit/
                test_google_client.py
                test_google_tools.py
                ...
            integration/
                test_google_integration.py
        samples/ (optional)
            ...
        pyproject.toml
        README.md
        ...
    ...
samples/
    ...
pyproject.toml
README.md
LICENSE
uv.lock
.pre-commit-config.yaml
```

We might add a template subpackage as well, to make it easy to setup, this could be based on the first one that is added.

In the [`DEV_SETUP.md`](../../python/DEV_SETUP.md) we will add instructions for how to deal with the path depth issues, especially on Windows, where the maximum path length can be a problem.

#### Evolving the package structure
For each of the advanced components, we have two reason why we may split them into a folder, with an `__init__.py` and optionally a `_files.py`:
1. If the file becomes too large, we can split it into multiple `_files`, while still keeping the public interface in the `__init__.py` file, this is a non-breaking change
2. If we want to partially or fully move that code into a separate package.
In this case we do need to lazy load anything that was moved from the main package to the subpackage, so that existing code still works, and if the subpackage is not installed we can raise a meaningful error.

> **Important**: This setup means that in a users machine, the code from the main package and the code from any installed subpackages will be put in the same folder in their python installation, this means there cannot be name clashes between the contents of a subpackage with each other, or with the main package. So the first level inside of those subpackages should be unique, preferably the same as the subpackage name. A subpackage can contain anything that is useful and related to Agent Framework, in that case for i.e. Azure, that would mean the following structure:

```plaintext
<!-- inside the Azure subpackage: -->
agent_framework/
    azure/
        __init__.py
        _chat.py
        _embeddings.py
        _context_safety.py
        ...
```

## Coding standards

Coding standards will be maintained in the [`DEV_SETUP.md`](../../python/DEV_SETUP.md) file.

[tool.ruff.lint]
fixable = ["ALL"]
unfixable = []
select = [
    "ASYNC", # async checks
    "B", # bugbear checks
    "CPY", #copyright
    "D", #pydocstyle checks
    "E", #error checks
    "ERA", #remove connected out code
    "F", #pyflakes checks
    "FIX", #fixme checks
    "I", #isort
    "INP", #implicit namespace package
    "ISC", #implicit string concat
    "Q", # flake8-quotes checks
    "RET", #flake8-return check
    "RSE", #raise exception parantheses check
    "RUF", # RUF specific rules
    "SIM", #flake8-simplify check
    "T100", # Debugger,
    "TD", #todos
    "W", # pycodestyle warning checks
]
ignore = [
    "D100", #allow missing docstring in public module
    "D104", #allow missing docstring in public package
    "TD003", #allow missing link to todo issue
    "FIX002" #allow todo
]

[tool.ruff.format]
docstring-code-format = true

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
# Ignore all directories named `tests` and `samples`.
"tests/**" = ["D", "INP", "TD", "ERA001", "RUF"]
"samples/**" = ["D", "INP", "ERA001", "RUF"]
# Ignore all files that end in `_test.py`.
"*_test.py" = ["D"]
"*.ipynb" = ["CPY", "E501"]

[tool.ruff.lint.flake8-copyright]
notice-rgx = "^# Copyright \\(c\\) Microsoft\\. All rights reserved\\."
min-file-size = 1
```

### Tooling
uv and ruff are the main tools, for package management and code formatting/linting respectively.

#### Type checking
We currently can choose between mypy, pyright, ty and pyrefly for static type checking.
I propose we run `mypy` and `pyright` in GHA, similar to what AG already does. We might explore newer tools as a later date.

#### Task runner
AG already has experience with poe the poet, so let's start there, removing the MAKE file setup that SK uses.

### Unit test coverage
The goal is to have at least 80% unit test coverage for all code under both the main package and the subpackages.

### Telemetry and logging
Telemetry and logging are handled by the `agent_framework.telemetry` and `agent_framework._logging` packages.

#### Logging

Logging is considered as part of the basic setup, while telemetry is a advanced concept.
The telemetry package will use OpenTelemetry to provide a consistent way to collect and export telemetry data, similar to how we do this now in SK.

The logging will be simplified, there will be one logger in the base package:
* name: `agent_framework` - used for all logging in the abstractions and base components

Each of the other subpackages for connectors will have a similar single logger.
* name: `agent_framework.openai`
* name: `agent_framework.azure`

This means that when a logger is needed, it should be created like this:
```python
from agent_framework import get_logger

logger = get_logger()
#or in a subpackage:
logger = get_logger('agent_framework.openai')
```
The implementation should be something like this:
```python
# in file _logging.py
import logging

def get_logger(name: str = "agent_framework") -> logging.Logger:
    """
    Get a logger with the specified name, defaulting to 'agent_framework'.

    Args:
        name (str): The name of the logger. Defaults to 'agent_framework'.

    Returns:
        logging.Logger: The configured logger instance.
    """
    logger = logging.getLogger(name)
    # create the specifics for the logger, such as setting the level, handlers, etc.
    return logger
```
This will ensure that the logger is created with the correct name and configuration, and it will be consistent across the package.

Further there should be a easy way to configure the log levels, either through a environment variable or with a similar function as the get_logger.

This will not be allowed:
```python
import logging

logger = logging.getLogger(__name__)
```

This is allowed but discouraged, if the get_logger function has been called at least once then this will return the same logger as the get_logger function, however that might not have happened and then the logging experience (in terms of formats and handlers, etc) is not consistent across the package:
```python
import logging

logger = logging.getLogger("agent_framework")
```

#### Telemetry
Telemetry will be based on OpenTelemetry (OTel), and will be implemented in the `agent_framework.telemetry` package.

We will also add headers with user-agent strings where applicable, these will include `agent-framework-python` and the version.

We should consider auto-instrumentation and provide an implementation of it to the OTel community.

### Build and release
The build step will be done in GHA, adding the package to the release and then we call into Azure DevOps to use the ESRP pipeline to publish to pypi. This is how SK already works, we will just have to adapt it to the new package structure.

For now we will stick to semantic versioning, and all preview release will be tagged as such.
