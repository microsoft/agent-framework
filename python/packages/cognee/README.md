# Get Started with Microsoft Agent Framework Cognee

Please install this package via pip:

```bash
pip install agent-framework-cognee --pre
```

## Cognee Tools

The Cognee integration provides AI function tools that enable agents to store and retrieve information using [Cognee](https://github.com/topoteretes/cognee), an open source AI memory for Agents, that builds knowledge graphs backed by embeddings from your data.

### Features

- **Knowledge Storage**: Store information in a knowledge graph for later retrieval
- **Semantic Search**: Search stored information using natural language queries
- **Session Isolation**: Scope data to specific sessions using `get_cognee_tools(session_id)`
- **Batched Processing**: Automatic batching of add operations for performance

### Requirements

- `OPENAI_API_KEY` environment variable
- `LLM_API_KEY` environment variable (used by Cognee)

### Known Limitations

> **Note:** `agent-framework-cognee` cannot be installed alongside `agent-framework-lab[lightning]` due to a dependency conflict between `cognee` and `litellm[proxy]` regarding `python-multipart` versions. Install cognee separately.
>
> **Upstream issue:** [BerriAI/litellm#9893](https://github.com/BerriAI/litellm/issues/9893) - `python-multipart: ^0.0.18` constraint is too restrictive.

### Basic Usage

```python
import asyncio
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from agent_framework.cognee import cognee_add, cognee_search

async def main():
    client = OpenAIChatClient(model_id="gpt-4o-mini")
    agent = ChatAgent(
        client,
        instructions="Use cognee_add to store information and cognee_search to find it.",
        tools=[cognee_add, cognee_search],
    )
    
    await agent.run("Remember that my favorite color is blue.")
    result = await agent.run("What is my favorite color?")
    print(result)

asyncio.run(main())
```

### Session-Scoped Usage

Use `get_cognee_tools` to create tools that isolate data by session:

```python
from agent_framework.cognee import get_cognee_tools

# Create session-scoped tools
add_tool, search_tool = get_cognee_tools("user-123")

agent = ChatAgent(
    client,
    instructions="Store and search information.",
    tools=[add_tool, search_tool],
)
```

### Example

See the [Cognee example](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/context_providers/cognee/cognee_openai.py) which demonstrates:

- Setting up an agent with Cognee tools
- Storing information with session isolation
- Retrieving information
- Multi-session data isolation

### Cognee Configuration

Before using, configure Cognee's data directories:

```python
import cognee
from cognee.api.v1.config import config

config.data_root_directory("./cognee_data")
config.system_root_directory("./cognee_system")

# Optional: Reset data for a fresh start
await cognee.prune.prune_data()
await cognee.prune.prune_system(metadata=True)
```

### API Reference

#### `cognee_add`

Store information in the knowledge base.

```python
@ai_function
async def cognee_add(
    data: str,           # The text to store
    node_set: list[str] | None = None,  # Optional session identifiers
) -> str
```

#### `cognee_search`

Search the knowledge base.

```python
@ai_function
async def cognee_search(
    query_text: str,     # Natural language search query
    node_name: list[str] | None = None,  # Optional filter by node names
) -> list[Any]
```

#### `get_cognee_tools`

Get session-scoped tools.

```python
def get_cognee_tools(
    session_id: str | None = None,  # Session ID (auto-generated if None)
) -> tuple[AIFunction, AIFunction]  # (add_tool, search_tool)
```
