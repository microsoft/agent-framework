# Python Package design for Agent Framework

## Design goals
* Developer experience is key
    * the components needed for a basic agent with tools and a runtime should be importable from `agent_framework` without having to import from subpackages. This will be referred to as _tier 0_ components.
    * for more advanced components, _tier 1_ components, such as context providers, guardrails, vector data, text search, exceptions, evaluation, utils, telemetry and workflows, they should be importable from `agent_framework.<component>`, so for instance `from agent_framework.vector_data import vectorstoremodel`.
    * for connectors (_tier 2_), a developer should never have to import from more than 2 levels deep
        * i.e.: `from agent_framework.connectors.openai import OpenAIClient`
        * Question: should we shorten this even further: either `from agent_framework.openai import OpenAIClient` or maybe something like `from agent_framework.ext.openai import OpenAIClient`?
    * if a single file becomes too cumbersome (files are allowed to be 1k+ lines) it should be split into a folder with an `__init__.py` that exposes the public interface and a `_files.py` that contains the implementation details, with a `__all__` in the init to expose the right things, if there are very large dependencies being loaded it can optionally using lazy loading to avoid loading the entire package when importing a single component.
    * as much as possible, related things are in a single file which makes understanding the code easier.
    * simple and straightforward logging and telemetry setup, so developers can easily add logging and telemetry to their code without having to worry about the details.
* Independence of connectors
    * To allow connectors to be treated as independent packages, we will use namespace packages for connectors, in principle this only includes the packages that we will develop in our repo, since that is easy to manage and maintain.
    * further advantages are that each package can have a independent lifecycle, versioning, and dependencies.
    * and this gives us insights into the usage, through pip install statistics, especially for connectors to services outside of Microsoft.
    * the goal is to group related connectors based on vendors, not on types, so for instance doing: `import agent_framework.connectors.google` will import connectors for all Google services, such as `GoogleChatClient` but also `BigQueryCollection`, etc.
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
from agent_framework import Agent, ai_tool
from agent_framework.connectors.openai import OpenAIChatClient

@ai_tool(description="Get the current weather in a given location")
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
    * tier 0 components, will be exposed directly from `agent_framework`:
        * (single) agents (includes threads)
        * tools (includes MCP and OpenAPI)
        * models/types (name tbd, will include the equivalent of MEAI for dotnet; content types and client abstractions)
        * logging
    * tier 1 components, will be exposed from `agent_framework.<component>`:
        * context_providers (tbd)
        * guardrails / filters
        * vector_data (vector stores and other MEVD pieces)
        * text_search
        * exceptions
        * evaluations
        * utils (optional)
        * telemetry (could also be observability or monitoring)
        * workflows (includes multi-agent orchestration)
    * connectors (namespace package), with these two potentially always installed:
        * openai
        * azure
        * will be exposed through i.e. `agent_framework.connectors.openai` and `agent_framework.connectors.azure`
* tests
* samples
* packages
    * openai
    * azure
    * ...

All the init's will use lazy loading so avoid importing the entire package when importing a single component.
Internal imports will be done using relative imports, so that the package can be used as a namespace package.

### File structure
The file structure will be as follows:

```plaintext
packages/
    redis/
        ...
    openai/
        src/
            agent_framework/
                connectors/
                    openai/
                        __init__.py
                        _chat.py
                        _embeddings.py
                        ...
        tests/
            ...
        samples/ (optional)
            ...
        pyproject.toml
        README.md
        ...
    google/
        src/
            agent_framework/
                connectors/
                    google/
                        __init__.py
                        _chat.py
                        _bigquery.py
                        ...
        tests/
            ...
        samples/ (optional)
            ...
        pyproject.toml
        README.md
        ...
    ...
src/
    agent_framework/
        __init__.py
        __init__.pyi
        _agents.py
        _tools.py
        _models.py
        _logging.py
        connectors/
            __init__.py
            README.md       
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
    __init__.py
    unit/
        conftest.py
        test_agents.py
        test_types.py
        ...
    integration/
        test_openai.py
        test_azure.py
        test_google.py
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

## Coding standards

* We use google docstyles for docstrings. 
* We use the following setup for ruff:
```toml
[tool.ruff]
line-length = 120
target-version = "py310"
include = ["*.py", "*.pyi", "**/pyproject.toml", "*.ipynb"]
preview = true

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
Logging is considered as part of the basic setup, while telemetry is a advanced concept.
The telemetry package will use OpenTelemetry to provide a consistent way to collect and export telemetry data, similar to how we do this now in SK.
The logging will be simplified, there will be one logger in the base package:
* `agent_framework`: for general logging

Each of the other subpackages for connectors will have a similar single logger.
* `agent_framework.connectors.openai`: for connector-specific logging
* `agent_framework.connectors.azure`: for connector-specific logging

This means that when a logger is needed, it should be created like this:
```python
from agent_framework import get_logger

logger = get_logger()
#or in a subpackage:
logger = get_logger('agent_framework.connectors.openai')
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

### Function definitions
To make the code easier to use, we will be very deliberate about the ordering and marking of function parameters.
This means that we will use the following conventions:
* Only parameters that are fully expected to be passed and only if there are a very limited number of them, let's say 3 or less, can they be supplied as positional parameters (still with a keyword, _almost_ never positional only).
* All other parameters should be supplied as keyword parameters, this is especially important to configure correctly when using Pydantic or dataclasses.
* If there are multiple required parameters, and they do not have a order that is common sense, then they will all use keyword parameters.
* If we use `kwargs` we will document how and what we use them for, this might be a reference to a outside package's documentation or an explanation of what the `kwargs` are used for.
* If we want to combine `kwargs` for multiple things, such as partly for a external client constructor, and partly for our own use, we will try to keep those separate, by adding a parameter, such as `client_kwargs` with type `dict[str, Any]`, and then use that to pass the kwargs to the client constructor (by using `Client(**client_kwargs)`), while using the `**kwargs` parameters for other uses, which are then also well documented.


### Build and release
The build step will be done in GHA, adding the package to the release and then we call into Azure DevOps to use the ESRP pipeline to publish to pypi. This is how SK already works, we will just have to adapt it to the new package structure.

# Open questions

* Should we shorten this even further: either `from agent_framework.openai import OpenAIClient` or maybe something like `from agent_framework.ext.openai import OpenAIClient`?
* Do we need filters? and what about filters vs guardrails?
* What do we want to do with Semantic Kernel templates? Or is context providers the new way of making "instructions" dynamic? And if we do want templates, do we need all three types currently in SK (SK, handlebars and jinja2) or just one, or even move to something like Prompty (already supported in .Net SK, not in python)?
* Do we want to separate other packages out into subpackages, like maybe telemetry, workflows, multi-agent orchestration, etc?
* what should be included when doing just `pip install agent-framework`, how can we minimize external dependencies?
    * in other words, which batteries should be included?
* What versioning scheme do we want to use, SemVer or CalVer?
* How do we want to generate API docs?
* Do we want to have a single logger for all AF, or should we have separate loggers for each component?
* What do we prefer, when the parameters are the same except for one, a Subclass or a Parameter, take: 
    ```python
    from autogen.models import UserMessage, AssistantMessage
    user_msg = UserMessage(
        content="Hello, world!"
    )
    asst_msg = AssistantMessage(
        content="Hello, world!"
    )
    #vs
    from semantic_kernel.contents import ChatMessageContent
    user_msg = ChatMessageContent(
        role="user",
        content="Hello, world!"
    )
    asst_msg = ChatMessageContent(
        role="assistant",
        content="Hello, world!"
    )
    ```
    There is no right or wrong here, it's a matter of preference but we need to be consistent. 
