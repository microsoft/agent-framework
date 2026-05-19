# MiniMax Package (agent-framework-minimax)

Integration with MiniMax's Anthropic-compatible API for Microsoft Agent Framework.

## Main Classes

- **`MiniMaxClient`** - Chat client for MiniMax models via Anthropic-compatible API
- **`RawMiniMaxClient`** - Raw client without middleware or telemetry
- **`MiniMaxSettings`** - Settings TypedDict for MiniMax configuration

## Supported Models

| Model ID | Description |
|----------|-------------|
| `MiniMax-M2.7` | Peak Performance. Ultimate Value. Master the Complex |
| `MiniMax-M2.7-highspeed` | Same performance, faster and more agile |

## Usage

```python
from agent_framework_minimax import MiniMaxClient

# Set MINIMAX_API_KEY environment variable, then:
client = MiniMaxClient(model="MiniMax-M2.7")
response = await client.get_response("Hello from MiniMax!")
```

## Import Path

```python
from agent_framework_minimax import MiniMaxClient
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MINIMAX_API_KEY` | Yes | MiniMax API key |
| `MINIMAX_CHAT_MODEL` | No | Default model to use |
| `MINIMAX_BASE_URL` | No | Override base URL (default: `https://api.minimax.io/anthropic`) |

## API Reference

- Chat (Anthropic Compatible): https://platform.minimax.io/docs/api-reference/text-anthropic-api
