# Get Started with Microsoft Agent Framework Google

Please install this package via pip:

```bash
pip install agent-framework-google --pre
```

## Google AI (Gemini API) Integration

This package provides integration with Google's Gemini API for Agent Framework:

- **Google AI (Gemini API)**: Direct access to Google's Gemini models with API key authentication

> **Note**: This package uses the new `google-genai` SDK as recommended by Google. See the [migration guide](https://ai.google.dev/gemini-api/docs/migrate) for more information.

### Current Features

**Available Now:**
- `GoogleAISettings`: Configuration class for Google AI (Gemini API) authentication and settings
- `GoogleAIChatClient`: Chat client for Google AI with streaming, function calling, and multi-turn conversation support
- Function calling with `@AIFunction` decorator and plain Python functions
- Multi-modal support (images)
- Full `ChatOptions` support (temperature, top_p, max_tokens, stop sequences)
- Usage tracking and OpenTelemetry observability

**Coming Soon:**
- Advanced features (context caching, safety settings, structured output)
- Thinking mode (Gemini 2.5)
- Enhanced error handling with retry policies

### Configuration

#### Google AI Settings

```python
from agent_framework_google import GoogleAISettings

# Configure via environment variables
# GOOGLE_AI_API_KEY=your_api_key
# GOOGLE_AI_CHAT_MODEL_ID=gemini-2.5-flash

settings = GoogleAISettings()

# Or pass parameters directly (pass SecretStr for type safety)
from pydantic import SecretStr

settings = GoogleAISettings(
    api_key=SecretStr("your_api_key"),
    chat_model_id="gemini-2.5-flash"
)
```

### Usage Examples

#### Basic Chat Completion

```python
import asyncio
from agent_framework import ChatMessage, Role, ChatOptions
from agent_framework_google import GoogleAIChatClient

async def main():
    # Configure via environment variables
    # GOOGLE_AI_API_KEY=your_api_key
    # GOOGLE_AI_CHAT_MODEL_ID=gemini-2.5-flash

    client = GoogleAIChatClient()

    # Create a simple chat message
    messages = [
        ChatMessage(role=Role.USER, text="What is the capital of France?")
    ]

    # Get response
    response = await client.get_response(
        messages=messages,
        chat_options=ChatOptions()
    )

    print(response.messages[0].text)
    # Output: Paris is the capital of France.

# Run the async function
asyncio.run(main())
```

#### Streaming Chat

```python
import asyncio
from agent_framework import ChatMessage, Role, ChatOptions
from agent_framework_google import GoogleAIChatClient

async def main():
    client = GoogleAIChatClient()

    messages = [
        ChatMessage(role=Role.USER, text="Write a short poem about programming.")
    ]

    # Stream the response
    async for chunk in client.get_streaming_response(
        messages=messages,
        chat_options=ChatOptions()
    ):
        if chunk.text:
            print(chunk.text, end="", flush=True)

# Run the async function
asyncio.run(main())
```

#### Chat with System Instructions

```python
import asyncio
from agent_framework import ChatMessage, Role, ChatOptions
from agent_framework_google import GoogleAIChatClient

async def main():
    client = GoogleAIChatClient()

    messages = [
        ChatMessage(role=Role.SYSTEM, text="You are a helpful coding assistant."),
        ChatMessage(role=Role.USER, text="How do I reverse a string in Python?")
    ]

    response = await client.get_response(
        messages=messages,
        chat_options=ChatOptions()
    )

    print(response.messages[0].text)

# Run the async function
asyncio.run(main())
```

#### Multi-Turn Conversation

```python
import asyncio
from agent_framework import ChatMessage, Role, ChatOptions
from agent_framework_google import GoogleAIChatClient

async def main():
    client = GoogleAIChatClient()

    messages = [
        ChatMessage(role=Role.USER, text="Hello! My name is Alice."),
        ChatMessage(role=Role.ASSISTANT, text="Hello Alice! Nice to meet you."),
        ChatMessage(role=Role.USER, text="What's my name?")
    ]

    response = await client.get_response(
        messages=messages,
        chat_options=ChatOptions()
    )

    print(response.messages[0].text)
    # Output: Your name is Alice!

# Run the async function
asyncio.run(main())
```

#### Customizing Generation Parameters

```python
import asyncio
from agent_framework import ChatMessage, Role, ChatOptions
from agent_framework_google import GoogleAIChatClient

async def main():
    client = GoogleAIChatClient()

    messages = [
        ChatMessage(role=Role.USER, text="Generate a creative story.")
    ]

    # Customize temperature and token limit
    chat_options = ChatOptions(
        temperature=0.9,  # Higher for more creativity
        max_tokens=500,
        top_p=0.95
    )

    response = await client.get_response(
        messages=messages,
        chat_options=chat_options
    )

    print(response.messages[0].text)

# Run the async function
asyncio.run(main())
```

## Configuration

### Environment Variables

**Google AI:**
- `GOOGLE_AI_API_KEY`: Your Google AI API key ([Get one here](https://aistudio.google.com/app/apikey))
- `GOOGLE_AI_CHAT_MODEL_ID`: Model to use (e.g., `gemini-2.5-flash`, `gemini-2.5-pro`)

### Supported Models

- `gemini-2.5-flash`: Best price-performance, recommended for most use cases (stable)
- `gemini-2.5-pro`: Advanced thinking model for complex reasoning (stable)
- `gemini-2.0-flash`: Previous generation workhorse model (stable)
- `gemini-1.5-pro`: Legacy stable model
- `gemini-1.5-flash`: Legacy fast model

## Features

### Current Features
- ✅ Chat completion (streaming and non-streaming)
- ✅ System instructions
- ✅ Conversation history management
- ✅ Usage/token tracking
- ✅ Customizable generation parameters (temperature, max_tokens, top_p, stop)
- ✅ Function/tool calling (`@AIFunction` and plain Python functions)
- ✅ Multi-modal support (images)
- ✅ OpenTelemetry observability

### Planned Features
- 🚧 Context caching
- 🚧 Safety settings configuration
- 🚧 Structured output (JSON mode)
- 🚧 Thinking mode (Gemini 2.5)

## Development Status

This package is being developed incrementally:

- ✅ **Phase 1**: Package structure and settings classes
- ✅ **Phase 2**: Google AI chat client with streaming, function calling, and multi-modal support
- 🚧 **Phase 3**: Advanced features (context caching, safety settings, thinking mode)
- 🚧 **Phase 4**: Integration tests and comprehensive samples

## Additional Information

For more information:
- [Google AI Studio](https://aistudio.google.com/) - Get an API key and test models
- [Google AI Documentation](https://ai.google.dev/gemini-api/docs)
- [Google GenAI SDK Migration Guide](https://ai.google.dev/gemini-api/docs/migrate)
- [Agent Framework Documentation](https://aka.ms/agent-framework)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
