# Ollama Examples

This folder contains examples demonstrating how to use Ollama models with the Agent Framework.

## Prerequisites

1. **Install Ollama**: Download and install Ollama from [ollama.com](https://ollama.com/)
2. **Start Ollama**: Ensure Ollama is running on your local machine
3. **Pull a model**: Run `ollama pull mistral` (or any other model you prefer)
   - For function calling examples, use models that support tool calling like `mistral` or `qwen2.5`
   - For reasoning examples, use models that support reasoning like `qwen2.5:8b`
   - For Multimodality you can use models like `gemma3:4b`

> **Note**: Not all models support all features. Function calling and reasoning capabilities depend on the specific model you're using.

## Examples

| File | Description |
|------|-------------|
| [`ollama_agent_basic.py`](ollama_agent_basic.py) | Demonstrates basic Ollama agent usage with the native Ollama Chat Client. Shows both streaming and non-streaming responses with tool calling capabilities. |
| [`ollama_agent_reasoning.py`](ollama_agent_reasoning.py) | Demonstrates Ollama agent with reasoning capabilities using the native Ollama Chat Client. Shows how to enable thinking/reasoning mode. |
| [`ollama_chat_client.py`](ollama_chat_client.py) | Ollama Chat Client with native Ollama Chat Client |
| [`ollama_chat_multimodal.py`](ollama_chat_multimodal.py) | Ollama Chat with multimodal native Ollama Chat Client |

## Configuration

The examples use environment variables for configuration. Set the appropriate variables based on which example you're running:

### For Native Ollama Examples (`ollama_agent_basic.py`, `ollama_agent_reasoning.py`)

Set the following environment variables:

- `OLLAMA_HOST`: The base URL for your Ollama server (optional, defaults to `http://localhost:11434`)
  - Example: `export OLLAMA_HOST="http://localhost:11434"`

- `OLLAMA_CHAT_MODEL_ID`: The model name to use
  - Example: `export OLLAMA_CHAT_MODEL_ID="qwen2.5:8b"`
  - Must be a model you have pulled with Ollama