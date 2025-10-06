# Ollama Examples

This folder contains examples demonstrating how to use Ollama models with the Agent Framework.

## Prerequisites

1. **Install Ollama**: Download and install Ollama from [ollama.com](https://ollama.com/)
2. **Start Ollama**: Ensure Ollama is running on your local machine
3. **Pull a model**: Run `ollama pull mistral` (or any other model you prefer that supports function calling)

## Examples

| File | Description |
|------|-------------|
| [`ollama_with_openai_chat_client.py`](ollama_with_openai_chat_client.py) | Demonstrates how to configure OpenAI Chat Client to use local Ollama models. Shows both streaming and non-streaming responses with tool calling capabilities. |

## Configuration

The examples use environment variables for configuration:

### Environment Variables

Set the following environment variables before running the examples:

- `OLLAMA_ENDPOINT`: The base URL for your Ollama server
  - Example: `export OLLAMA_ENDPOINT="http://localhost:11434/v1/"`

- `OLLAMA_MODEL`: The model name to use
  - Example: `export OLLAMA_MODEL="mistral"`
  - Must be a model you have pulled with Ollama
