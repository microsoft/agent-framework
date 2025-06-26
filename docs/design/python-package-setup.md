# Python Package design for Agent Framework


### Design goals
* Developer experience is key
    * this means shallow imports natively, a developer should never have to import from more than 2 levels deep for connectors and 1 level deep for everything else
    * i.e.: `from agent_framework.connectors.openai import OpenAIClient` or `from agent_framework.tools import Tool`
    * if a single file becomes too cumbersome (files can easily be 1k+ lines) it should be split into a folder with an `__init__.py` that exposes the public interface and a `_files.py` that contains the implementation details, with a `__all__` in the init to expose the right things.
    * simple and straightforward logging and telemetry setup, so developers can easily add logging and telemetry to their code without having to worry about the details.
* Namespace packages for connectors
    * To allow connectors to be treated as independent packages, we will use namespace packages for connectors, in principle this only includes the packages that we will develop in our repo, since that is easier to manage and maintain.
    * further advantages are that each package can have a independent lifecycle, versioning, and dependencies.
    * and this gives us insights into the usage, through pip install statistics, especially for connectors to services outside of Microsoft.
    * the goal is to group related connectors based on vendors, not on types, so for instance doing: `import agent_framework.connectors.google` will import connectors for all Google services, such as `GoogleChatClient` but also `BigQueryCollection`, etc.
    * All dependencies for a subpackage should be required dependencies in that package, and that package becomes a optional dependency in the main package as a extra with the same name, so in the main `pyproject.toml` we will have:
        ```toml
        [project.optional-dependencies]
        google = [
            "agent-framework-google == 1.0.0"
        ]
        ```
    * this means developers can install the main package with `pip install agent-framework[google]` to get all Google connectors, as well as manually installing the subpackage with `pip install agent-framework-google`.

Overall the following structure is proposed:
* packages
    * google
    * ...
* agent-framework
    * agents
    * connectors (namespace packages), with these two built-in/always installed:
        * openai
        * azure
    * context providers (tbd)
    * guardrails
    * data (vector stores, text search and other MEVD pieces)
    * exceptions
    * evaluation
    * tools (includes MCP and OpenAPI)
    * models/types (name tbd, will include the equivalent of MEAI for dotnet; content types and client abstractions)
    * utils (optional)
    * templates (maybe part of Tool)
    * telemetry (could also be observability or monitoring)
    * logging
    * workflows
* tests
* samples

## Telemetry and logging
Telemetry and logging are handled by the `agent_framework.telemetry` and `agent_framework.logging` packages.
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


## File structure
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
        py.typed
        agents.py
        connectors/
            __init__.py
            __init__.pyi
            openai.py
            azure.py
        context_providers.py
        guardrails.py
        data.py
        exceptions.py
        evaluation.py
        tools.py
        models.py
        telemetry.py
        logging.py
        utils.py
        templates.py
        workflows.py
tests/
    __init__.py
    unit/
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