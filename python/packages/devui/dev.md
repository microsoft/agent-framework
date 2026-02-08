# Testing DevUI - Quick Setup Guide

Here are the step-by-step instructions to test the new DevUI feature:

## 1. Get the Code

```bash
git clone https://github.com/microsoft/agent-framework.git
cd agent-framework
```

## 2. Setup Environment

Navigate to the Python directory and install dependencies:

```bash
cd python
uv sync --dev
source .venv/bin/activate
```

## 3. Configure Environment Variables

Create a `.env` file in the `python/` directory with your API credentials:

```bash
# Copy the example file
cp .env.example .env
```

Then edit `.env` and add your API keys:

```bash
# For OpenAI (minimum required)
OPENAI_API_KEY="your-api-key-here"
OPENAI_CHAT_MODEL_ID="gpt-4o-mini"

# Or for Azure OpenAI
AZURE_OPENAI_ENDPOINT="your-endpoint"
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="your-deployment-name"
```

## 4. Test DevUI

**Option A: In-Memory Mode (Recommended for quick testing)**

```bash
cd samples/getting_started/devui
python in_memory_mode.py
```

This runs a simple example with predefined agents and opens your browser automatically at http://localhost:8090

**Option B: Directory-Based Discovery**

```bash
cd samples/getting_started/devui
devui
```

This launches the UI with all example agents/workflows at http://localhost:8080

## 5. What You'll See

- A web interface for testing agents interactively
- Multiple example agents (weather assistant, general assistant, etc.)
- OpenAI-compatible API endpoints for programmatic access

## 6. API Testing (Optional)

You can also test via API calls:

### Single Request

```bash
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "weather_agent",
    "input": "What is the weather in Seattle?"
  }'
```

### Multi-turn Conversations

```bash
# Create a conversation
curl -X POST http://localhost:8080/v1/conversations \
  -H "Content-Type: application/json" \
  -d '{"metadata": {"agent_id": "weather_agent"}}'

# Returns: {"id": "conv_abc123", ...}

# Use conversation ID in requests
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "weather_agent",
    "input": "What is the weather in Seattle?",
    "conversation": "conv_abc123"
  }'

# Continue the conversation
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "weather_agent",
    "input": "How about tomorrow?",
    "conversation": "conv_abc123"
  }'
```

## API Mapping

Agent Framework content types → OpenAI Responses API events (in `_mapper.py`):

| Agent Framework Content         | OpenAI Event                             | Status   |
| ------------------------------- | ---------------------------------------- | -------- |
| `TextContent`                   | `response.output_text.delta`             | Standard |
| `TextReasoningContent`          | `response.reasoning.delta`               | Standard |
| `FunctionCallContent` (initial) | `response.output_item.added`             | Standard |
| `FunctionCallContent` (args)    | `response.function_call_arguments.delta` | Standard |
| `FunctionResultContent`         | `response.function_result.complete`      | DevUI    |
| `ErrorContent`                  | `response.error`                         | Standard |
| `UsageContent`                  | `response.usage.complete`                | Extended |
| `WorkflowEvent`                 | `response.workflow.event`                | DevUI    |
| `DataContent`, `UriContent`     | `response.trace.complete`                | DevUI    |

- **Standard** = OpenAI spec, **Extended** = OpenAI + extra fields, **DevUI** = DevUI-specific

## Frontend Development

```bash
cd python/packages/devui/frontend
yarn install

# Development (hot reload)
yarn dev

# Build (copies to backend ui/)
yarn build
```

## Running Tests

```bash
cd python/packages/devui

# All tests
pytest tests/ -v

# Specific suites
pytest tests/test_conversations.py -v  # Conversation store
pytest tests/test_server.py -v         # API endpoints
pytest tests/test_mapper.py -v         # Event mapping
```

## Troubleshooting

- **Missing API key**: Make sure your `.env` file is in the `python/` directory with valid credentials. Or set environment variables directly in your shell before running DevUI.
- **Import errors**: Run `uv sync --dev` again to ensure all dependencies are installed
- **Port conflicts**: DevUI uses ports 8080 and 8090 by default - close other services using these ports

Let me know if you run into any issues!
