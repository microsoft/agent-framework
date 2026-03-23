# Get Started with Microsoft Agent Framework Gemini

Install the provider package:

```bash
pip install agent-framework-gemini --pre
```

## Gemini Integration

The Gemini integration enables Microsoft Agent Framework applications to call Google Gemini models with familiar chat abstractions, including streaming, tool/function calling, and structured output.

## Authentication

Obtain an API key from [Google AI Studio](https://aistudio.google.com/apikey) and set it via environment variable:

```bash
export GEMINI_API_KEY="your-api-key"
export GEMINI_CHAT_MODEL_ID="gemini-2.5-flash"
```

## Examples

See the [Google Gemini samples](../../samples/02-agents/providers/google/) for runnable end-to-end scripts covering:

- Basic agent with tool calling and streaming
- Extended thinking with `ThinkingConfig`
- Google Search grounding
- Built-in code execution
