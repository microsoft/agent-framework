# Get Started with Microsoft Agent Framework Gemini

Install the provider package:

```bash
pip install agent-framework-gemini --pre
```

## Gemini Integration

The Gemini integration enables Microsoft Agent Framework applications to call Google Gemini models with familiar chat abstractions, including streaming, tool/function calling, and structured output.

## Authentication

The connector supports both `google-genai` authentication modes.

### Gemini Developer API

Obtain an API key from [Google AI Studio](https://aistudio.google.com/apikey) and set either the package-prefixed or SDK-standard environment variable:

```bash
export GEMINI_API_KEY="your-api-key"
# or: export GOOGLE_API_KEY="your-api-key"
export GEMINI_MODEL="gemini-2.5-flash-lite"
# or: export GOOGLE_MODEL="gemini-2.5-flash-lite"
```

### Vertex AI

Set the standard Vertex AI environment variables used by `google-genai`:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="global"
export GOOGLE_MODEL="gemini-2.5-flash-lite"
```

## Examples

See the [Google Gemini samples](samples/) for runnable end-to-end scripts covering:

- Basic agent with tool calling and streaming
- Extended thinking with `ThinkingConfig`
- Google Search grounding
- Google Maps grounding
- Built-in code execution
