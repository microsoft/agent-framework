# Get Started with Microsoft Agent Framework Google

> **Note**: This package is currently under active development. The chat client implementations for Google AI and Vertex AI are coming soon. This initial release provides the foundational settings and configuration classes.

Please install this package via pip:

```bash
pip install agent-framework-google --pre
```

## Google AI & Vertex AI Integration

This package will provide integration with Google's generative AI platforms:

- **Google AI (Gemini API)**: Direct access to Google's Gemini models with API key authentication
- **Vertex AI**: Enterprise-grade access via Google Cloud Platform with advanced features like grounding and code execution

### Current Status

**Available Now:**
- `GoogleAISettings`: Configuration class for Google AI (Gemini API) authentication and settings
- `VertexAISettings`: Configuration class for Vertex AI authentication and settings

**Coming Soon:**
- `GoogleAIChatClient`: Chat client for Google AI with streaming, function calling, and multi-modal support
- `VertexAIChatClient`: Enterprise chat client with grounding (Google Search) and code execution capabilities
- Integration tests and usage samples

### Configuration

You can configure the settings classes now, which will be used by the chat clients in the next release:

#### Google AI Settings

```python
from agent_framework_google import GoogleAISettings

# Configure via environment variables
# GOOGLE_AI_API_KEY=your_api_key
# GOOGLE_AI_MODEL_ID=gemini-1.5-pro

settings = GoogleAISettings()

# Or pass parameters directly
settings = GoogleAISettings(
    api_key="your_api_key",
    model_id="gemini-1.5-pro"
)
```

#### Vertex AI Settings

```python
from agent_framework_google import VertexAISettings

# Configure via environment variables
# VERTEX_AI_PROJECT_ID=your-project-id
# VERTEX_AI_LOCATION=us-central1
# VERTEX_AI_MODEL_ID=gemini-1.5-pro
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json

settings = VertexAISettings()

# Or pass parameters directly
settings = VertexAISettings(
    project_id="your-project-id",
    location="us-central1",
    model_id="gemini-1.5-pro"
)
```

### Future Usage (Coming Soon)

Once the chat clients are released, usage will look like this:

#### Google AI (Gemini API)

Use Google AI for straightforward access to Gemini models with API key authentication.

```python
from agent_framework.google import GoogleAIChatClient

# Configure via environment variables
# GOOGLE_AI_API_KEY=your_api_key
# GOOGLE_AI_MODEL_ID=gemini-1.5-pro

client = GoogleAIChatClient()
agent = client.create_agent(
    name="Assistant",
    instructions="You are a helpful assistant"
)

response = await agent.run("Hello!")
print(response.text)
```

#### Vertex AI (Coming Soon)

Use Vertex AI for enterprise features including grounding with Google Search and code execution.

```python
from agent_framework.google import VertexAIChatClient
from agent_framework import HostedWebSearchTool

# Configure via environment variables
# VERTEX_AI_PROJECT_ID=your-project-id
# VERTEX_AI_LOCATION=us-central1
# VERTEX_AI_MODEL_ID=gemini-1.5-pro
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json

client = VertexAIChatClient()
agent = client.create_agent(
    name="Assistant",
    instructions="You are a helpful assistant",
    tools=[HostedWebSearchTool()]  # Vertex AI exclusive
)

response = await agent.run("What's the latest news?")
print(response.text)
```

## Configuration

### Environment Variables

**Google AI:**
- `GOOGLE_AI_API_KEY`: Your Google AI API key ([Get one here](https://ai.google.dev/))
- `GOOGLE_AI_MODEL_ID`: Model to use (e.g., `gemini-1.5-pro`, `gemini-1.5-flash`)

**Vertex AI:**
- `VERTEX_AI_PROJECT_ID`: Your GCP project ID
- `VERTEX_AI_LOCATION`: GCP region (e.g., `us-central1`)
- `VERTEX_AI_MODEL_ID`: Model to use (e.g., `gemini-1.5-pro`)
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account JSON file

### Supported Models

- `gemini-1.5-pro`: Most capable model
- `gemini-1.5-flash`: Faster, cost-effective model
- `gemini-2.0-flash-exp`: Experimental latest model

## Features

### Common Features (Both Google AI & Vertex AI)
- ✅ Chat completion (streaming and non-streaming)
- ✅ Function/tool calling
- ✅ Multi-modal support (text, images, video, audio)
- ✅ System instructions
- ✅ Conversation history management

### Vertex AI Exclusive Features (Coming Soon)
- Grounding with Google Search
- Grounding with Vertex AI Search
- Code execution tool
- Enterprise security and compliance
- VPC-SC support

## Development Roadmap

This package is being developed incrementally:

- ✅ **Phase 1 (Current)**: Package structure and settings classes
- 🚧 **Phase 2 (Next)**: Google AI chat client with streaming and function calling
- 🚧 **Phase 3**: Google AI integration tests and samples
- 🚧 **Phase 4**: Vertex AI chat client with enterprise features
- 🚧 **Phase 5**: Vertex AI integration tests and samples
- 🚧 **Phase 6**: Advanced features (context caching, safety settings, etc.)

## Examples

Examples will be available once the chat clients are implemented. Check back soon or watch the [repository](https://github.com/microsoft/agent-framework) for updates.

## Documentation

For more information:
- [Google AI Documentation](https://ai.google.dev/docs)
- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Agent Framework Documentation](https://aka.ms/agent-framework)
- [Agent Framework Repository](https://github.com/microsoft/agent-framework)
