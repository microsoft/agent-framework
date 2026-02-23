# Ollama Examples

This folder contains examples demonstrating how to use Ollama models with the Agent Framework.

## Prerequisites

1. **Install Ollama**: Download and install Ollama from [ollama.com](https://ollama.com/)
2. **Start Ollama**: Ensure Ollama is running on your local machine
3. **Pull a model**: Run `ollama pull mistral` (or any other model you prefer)
   - For function calling examples, use models that support tool calling like `mistral` or `qwen2.5`
   - For reasoning examples, use models that support reasoning like `qwen3:8b`
   - For multimodal examples, use models like `gemma3:4b`

> **Note**: Not all models support all features. Function calling, reasoning, and multimodal capabilities depend on the specific model you're using.

## Recommended Approach

The recommended way to use Ollama with Agent Framework is via the native `OllamaChatClient` from the `agent-framework-ollama` package. This provides full support for Ollama-specific features like reasoning mode.

Alternatively, you can use the `OpenAIChatClient` configured to point to your local Ollama server, which may be useful if you're already familiar with the OpenAI client interface.

## Examples

| File | Description |
|------|-------------|
| [`ollama_agent_basic.py`](ollama_agent_basic.py) | Basic Ollama agent with tool calling using native Ollama Chat Client. Shows both streaming and non-streaming responses. |
| [`ollama_agent_reasoning.py`](ollama_agent_reasoning.py) | Ollama agent with reasoning capabilities using native Ollama Chat Client. Shows how to enable thinking/reasoning mode. |
| [`ollama_chat_client.py`](ollama_chat_client.py) | Direct usage of the native Ollama Chat Client with tool calling. |
| [`ollama_chat_multimodal.py`](ollama_chat_multimodal.py) | Ollama Chat Client with multimodal (image) input capabilities. |
| [`ollama_with_openai_chat_client.py`](ollama_with_openai_chat_client.py) | Alternative approach using OpenAI Chat Client configured to use local Ollama models. |

## Configuration

The examples use environment variables for configuration. Set the appropriate variables based on which example you're running:

### For Native Ollama Examples

Set the following environment variables:

- `OLLAMA_HOST`: The base URL for your Ollama server (optional, defaults to `http://localhost:11434`)
  - Example: `export OLLAMA_HOST="http://localhost:11434"`

- `OLLAMA_MODEL_ID`: The model name to use
  - Example: `export OLLAMA_MODEL_ID="qwen2.5:8b"`
  - Must be a model you have pulled with Ollama

### For OpenAI Client with Ollama (`ollama_with_openai_chat_client.py`)

Set the following environment variables:

- `OLLAMA_ENDPOINT`: The base URL for your Ollama server with `/v1/` suffix
  - Example: `export OLLAMA_ENDPOINT="http://localhost:11434/v1/"`

- `OLLAMA_MODEL`: The model name to use
  - Example: `export OLLAMA_MODEL="mistral"`
  - Must be a model you have pulled with Ollama