# Python Package design for Agent Framework


## Design goals
* Developer experience is key
    * the components needed for a basic agent with tools and a runtime should be importable from `agent_framework` without having to import from subpackages. This will be referred to as _tier 0_ components.
    * for more complex pieces, a developer should never have to import from more than 2 levels deep for connectors and 1 level deep for everything else
        * i.e.: `from agent_framework.connectors.openai import OpenAIClient` or `from agent_framework import Tool`
        * this will be referred to as _tier 1_ components.
    * if a single file becomes too cumbersome (files can easily be 1k+ lines) it should be split into a folder with an `__init__.py` that exposes the public interface and a `_files.py` that contains the implementation details, with a `__all__` in the init to expose the right things.
    * as much as possible, related things are in a single file which makes understanding the code easier.
    * simple and straightforward logging and telemetry setup, so developers can easily add logging and telemetry to their code without having to worry about the details.
* Independence of connectors
    * To allow connectors to be treated as independent packages, we will use namespace packages for connectors, in principle this only includes the packages that we will develop in our repo, since that is easier to manage and maintain.
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
from agent_framework import Agent, tool
from agent_framework.connectors.openai import OpenAIChatClient

@tool(description="Get the current weather in a given location")
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

## Package structure
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
        * vector_data (vector stores, text search and other MEVD pieces)
        * text_search
        * exceptions
        * evaluation
        * utils (optional)
        * telemetry (could also be observability or monitoring)
        * workflows (includes multi-agent orchestration)
    * connectors (namespace packages), with these two built-in/always installed:
        * openai
        * azure
        * will be exposed through i.e. `agent_framework.connectors.openai` and `agent_framework.connectors.azure`
* tests
* samples
* packages
    * google
    * ...

All the init's will use lazy loading so avoid importing the entire package when importing a single component.
Internal imports will be done using relative imports, so that the package can be used as a namespace package.

### File structure
The file structure will be as follows:

```plaintext
packages/
    redis/
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
src/
    agent_framework/
        __init__.py
        __init__.pyi
        py.typed
        _agents.py
        connectors/
            __init__.py
            __init__.pyi
            openai.py
            azure.py
        context_providers.py
        guardrails.py
        exceptions.py
        evaluation.py
        _tools.py
        _models.py
        _logging.py
        utils.py
        telemetry.py
        templates.py
        text_search.py
        vector_data.py
        workflows.py
tests/
    __init__.py
    unit/
        conftest.py
        test_agents.py
        test_connectors.py
        ...
    integration/
        test_openai.py
        test_azure.py
        test_google.py (will run with google connector installed)
        ...
samples/
    ...
pyproject.toml
README.md
LICENSE
uv.lock
.pre-commit-config.yaml
```

## Coding standards

### Telemetry and logging
Telemetry and logging are handled by the `agent_framework.telemetry` and `agent_framework._logging` packages.
Logging is considered as part of the basic setup, while telemetry is a advanced concept.
The telemetry package will use OpenTelemetry to provide a consistent way to collect and export telemetry data, similar to how we do this now in SK.
The logging will be simplified, there will be three loggers in the base package:
* `agent_framework`: for general logging
* `agent_framework.connectors.openai`: for connector-specific logging
* `agent_framework.connectors.azure`: for connector-specific logging
Each of the other subpackages for connectors will have a similar single logger.
This means that when a logger is needed, it should be created like this:
```python
from agent_framework.logging import get_logger

logger = get_logger("agent_framework")
```
This will ensure that the logger is created with the correct name and configuration, and it will be consistent across the package, so this will not be allowed:
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
* If we want to combine `kwargs` for multiple things, such as partly for a external client constructor, and partly for our own use, we will try to keep those separate, by adding a parameter, such as `client_kwargs` with type `dict[str, Any]`, and then use that to pass the kwargs to the client constructor (by using `Client(**client_kwargs)`), while using the `**kwargs` parameters for our own use.


# Open questions

* Do we need filters? and what about filters vs guardrails?
* What do we want to do with templates? Or is context providers the new way of making "instructions" dynamic?
* Do we want to separate other packages out into subpackages, like maybe telemetry, workflows, multi-agent orchestration, etc?
* What versioning scheme do we want to use, SemVer or CalVer?
* Style question: What do we prefer, when the parameters are the same except for one, a Subclass or a Parameter, take: 
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
