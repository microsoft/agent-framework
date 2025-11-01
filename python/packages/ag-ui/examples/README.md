# AG-UI Examples

Example implementations of all AG-UI features using Agent Framework.

## Setup

1. Install the package and dependencies:
```bash
cd packages/ag-ui
uv pip install -e .
```

2. Set your Azure OpenAI credentials:
```bash
export AZURE_OPENAI_ENDPOINT="your-endpoint"
export AZURE_OPENAI_API_KEY="your-key"
```

3. Run the example server:
```bash
cd packages/ag-ui/examples
python -m .
```

The server will start on http://localhost:8888

## Available Endpoints

### 1. Agentic Chat (`/agentic_chat`)

Basic conversational agent with streaming responses.

**Agent:** `simple_agent.py`

**Features:**
- Streaming text responses
- Basic conversation handling

### 2. Backend Tool Rendering (`/backend_tool_rendering`)

Agent with tools that execute on the backend and stream results to the frontend.

**Agent:** `weather_agent.py`

**Available Tools:**
- `get_weather(location: str)` - Get current weather for a location
- `get_forecast(location: str, days: int)` - Get weather forecast

**Example Request:**
```bash
curl -X POST http://localhost:8000/backend_tool_rendering \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is the weather in Seattle?"}
    ]
  }'
```

**Features:**
- Tool call streaming (ToolCallStartEvent, ToolCallArgsEvent, ToolCallEndEvent)
- Tool result streaming (ToolCallResultEvent)
- Multiple tool calls in sequence

## Creating Your Own Agents

To create a new agent:

1. Create a new file in `agents/`:
```python
from agent_framework import ChatAgent, ai_function
from agent_framework.azure import AzureOpenAIChatClient

@ai_function
def my_tool(param: str) -> str:
    """My custom tool."""
    return f"Result for {param}"

my_agent = ChatAgent(
    name="my_agent",
    instructions="Your instructions here",
    chat_client=AzureOpenAIChatClient(model_id="gpt-4o"),
    tools=[my_tool],
)
```

2. Add it to the server in `server/main.py`:
```python
from agents.my_agent import my_agent

add_agent_framework_fastapi_endpoint(
    app=app,
    agent=my_agent,
    path="/my_feature",
)
```
python server/main.py
```

## Available Endpoints

- `/agentic_chat` - Basic chat with streaming

## Testing

You can test endpoints with curl:
```bash
curl -X POST http://localhost:8000/agentic_chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello!"}],
    "thread_id": "test-thread"
  }'
```
