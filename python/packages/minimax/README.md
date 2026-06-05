# Get Started with Microsoft Agent Framework MiniMax

Please install this package via pip:

```bash
pip install agent-framework-minimax --pre
```

## MiniMax Integration

The MiniMax integration enables communication with MiniMax's Anthropic-compatible API,
allowing your Agent Framework applications to leverage MiniMax's powerful language models.

### Environment Variables

Set the following environment variables before using the client:

```bash
export MINIMAX_API_KEY="your_minimax_api_key"
```

### Basic Usage Example

```python
import asyncio
from agent_framework_minimax import MiniMaxClient

async def main():
    client = MiniMaxClient(model="MiniMax-M3")
    response = await client.get_response("Hello! Tell me about yourself.")
    print(response.messages[0].text)

asyncio.run(main())
```

### Streaming Example

```python
import asyncio
from agent_framework_minimax import MiniMaxClient

async def main():
    client = MiniMaxClient(model="MiniMax-M3")
    async for update in await client.get_streaming_response("Tell me a short story."):
        if update.text:
            print(update.text, end="", flush=True)
    print()

asyncio.run(main())
```

### Supported Models

| Model | Description |
|-------|-------------|
| `MiniMax-M3` | Latest model, 512K context, up to 128K output, supports image input (default) |
| `MiniMax-M2.7` | Previous generation |
| `MiniMax-M2.7-highspeed` | Previous generation, faster and more agile |

### API Documentation

- Chat (Anthropic Compatible): https://platform.minimax.io/docs/api-reference/text-anthropic-api
