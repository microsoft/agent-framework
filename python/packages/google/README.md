# Get Started with Microsoft Agent Framework Google

> **Note**: This package is currently under active development. The chat client implementation for Google AI is coming soon. This initial release provides the foundational settings and configuration classes.

Please install this package via pip:

```bash
pip install agent-framework-google --pre
```

## Google AI (Gemini API) Integration

This package provides integration with Google's Gemini API for Agent Framework:

- **Google AI (Gemini API)**: Direct access to Google's Gemini models with API key authentication

> **Note**: This package uses the new `google-genai` SDK as recommended by Google. See the [migration guide](https://ai.google.dev/gemini-api/docs/migrate) for more information.

### Current Status

**Available Now:**
- `GoogleAISettings`: Configuration class for Google AI (Gemini API) authentication and settings

**Coming Soon:**
- `GoogleAIChatClient`: Chat client for Google AI with streaming, function calling, and multi-modal support
- Integration tests and usage samples

### Configuration

You can configure the settings class now, which will be used by the chat client in the next release:

#### Google AI Settings

```python
from agent_framework_google import GoogleAISettings

# Configure via environment variables
# GOOGLE_AI_API_KEY=your_api_key
# GOOGLE_AI_CHAT_MODEL_ID=gemini-1.5-pro

settings = GoogleAISettings()

# Or pass parameters directly (pass SecretStr for type safety)
from pydantic import SecretStr

settings = GoogleAISettings(
    api_key=SecretStr("your_api_key"),
    chat_model_id="gemini-1.5-pro"
)
```

### Future Usage (Coming Soon)

Once the chat client is released, usage will look like this:

```python
# from agent_framework.google import GoogleAIChatClient
#
# # Configure via environment variables
# # GOOGLE_AI_API_KEY=your_api_key
# # GOOGLE_AI_CHAT_MODEL_ID=gemini-1.5-pro
#
# client = GoogleAIChatClient()
# agent = client.create_agent(
#     name="Assistant",
#     instructions="You are a helpful assistant"
# )
#
# response = await agent.run("Hello!")
# print(response.text)
```

## Configuration

### Environment Variables

**Google AI:**
- `GOOGLE_AI_API_KEY`: Your Google AI API key ([Get one here](https://ai.google.dev/))
- `GOOGLE_AI_CHAT_MODEL_ID`: Model to use (e.g., `gemini-1.5-pro`, `gemini-1.5-flash`)

### Supported Models

- `gemini-1.5-pro`: Most capable model
- `gemini-1.5-flash`: Faster, cost-effective model
- `gemini-2.0-flash-exp`: Experimental latest model

## Features

### Planned Features
- ✅ Chat completion (streaming and non-streaming)
- ✅ Function/tool calling
- ✅ Multi-modal support (text, images, video, audio)
- ✅ System instructions
- ✅ Conversation history management

## Development Roadmap

This package is being developed incrementally:

- ✅ **Phase 1 (Current)**: Package structure and settings classes
- 🚧 **Phase 2 (Next)**: Google AI chat client with streaming and function calling
- 🚧 **Phase 3**: Google AI integration tests and samples
- 🚧 **Phase 4**: Advanced features (context caching, safety settings, structured output)

> **Note**: Vertex AI support may be added in a future iteration based on user demand.

## Examples

Examples will be available once the chat client is implemented. Check back soon or watch the [repository](https://github.com/microsoft/agent-framework) for updates.

## Documentation

For more information:
- [Google AI Documentation](https://ai.google.dev/docs)
- [Google Gemini API Migration Guide](https://ai.google.dev/gemini-api/docs/migrate)
- [Agent Framework Documentation](https://aka.ms/agent-framework)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
