# Get Started with Microsoft Agent Framework Azure Voice Live

Please install this package via pip:

```bash
pip install agent-framework-azure-voice-live --pre
```

## Azure Voice Live Integration

The Azure Voice Live integration provides real-time voice conversation capabilities using Azure's Voice Live SDK, supporting bidirectional audio streaming with Azure Speech Services and generative AI models.

### Features

- **Real-time Audio Streaming**: Bidirectional audio communication with AI models
- **Voice Selection**: Support for OpenAI voices (alloy, echo, shimmer, etc.) and Azure Neural voices
- **Tool Calling**: Function calling support during voice conversations
- **Environment Variables**: Easy configuration via AZURE_VOICELIVE_* environment variables
- **Authentication**: Support for both API keys and Azure identity credentials

### Basic Usage Example

```python
from agent_framework import RealtimeAgent
from agent_framework_azure_voice_live import AzureVoiceLiveClient

# Create client
client = AzureVoiceLiveClient(
    endpoint="https://myresource.services.ai.azure.com",
    model="gpt-4o-realtime-preview",
    api_key="your-api-key",
)

# Create agent
agent = client.as_agent(
    name="voice-assistant",
    instructions="You are a helpful voice assistant.",
    voice="alloy",
)

# Run voice conversation
async for event in agent.run(audio_input=microphone_stream()):
    if event.type == "audio":
        play_audio(event.data["audio"])
```

For more examples, see the [Azure Voice Live examples](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents/azure_ai/).
