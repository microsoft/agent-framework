# ChatKit Package (agent-framework-chatkit)

Integration with OpenAI ChatKit (Python) for building chat UIs.

## Main Classes

- **`ThreadItemConverter`** - Converts between Agent Framework and ChatKit types
- **`stream_agent_response()`** - Stream agent responses to ChatKit
- **`simple_to_agent_input()`** - Convert simple input to agent input format

## Usage

```python
from agent_framework.chatkit import stream_agent_response, ThreadItemConverter

async for event in stream_agent_response(agent, messages):
    # Handle ChatKit events
    pass
```

## Import Path

```python
from agent_framework.chatkit import stream_agent_response
# or directly:
from agent_framework_chatkit import stream_agent_response
```
