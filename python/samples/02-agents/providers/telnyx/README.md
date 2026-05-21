# Telnyx Examples

This folder contains examples demonstrating how to use Telnyx as an OpenAI-compatible inference provider with the Agent Framework.

## Prerequisites

1. **Telnyx Account**: Sign up at [portal.telnyx.com](https://portal.telnyx.com/) and obtain an API key
2. **API Key**: Generate an API key from the Telnyx portal under "Auth Keys"

## Overview

Telnyx provides an OpenAI-compatible API at `https://api.telnyx.com/v2/ai/openai` that supports chat completions and embeddings. Since it's OpenAI-compatible, you can use the existing `OpenAIChatClient` and `OpenAIEmbeddingClient` from the `agent-framework-openai` package — no new provider package is needed.

This follows the same pattern as the [Ollama with OpenAI Chat Client](../ollama/ollama_with_openai_chat_client.py) example, where an existing provider client is configured with a custom `base_url`.

> **Note**: Available models depend on your Telnyx account configuration. Common models include Kimi-K2.5, GLM-5.1-FP8, MiniMax-M2.7, and Qwen3-235B-A22B. See the [Telnyx AI documentation](https://developers.telnyx.com/docs/api/ai) for the latest model list.

## Examples

| File | Description |
|------|-------------|
| `telnyx_chat_completion.py` | Basic chat completion using `OpenAIChatClient` with Telnyx endpoint. Shows both streaming and non-streaming responses. |
| `telnyx_embeddings.py` | Text embeddings using `OpenAIEmbeddingClient` with Telnyx endpoint. |

## Configuration

Set the following environment variables:

- `TELNYX_API_KEY` — Your Telnyx API key (required for all examples)
  - Get one from [portal.telnyx.com](https://portal.telnyx.com/) → Auth Keys
  - Example: `export TELNYX_API_KEY="KEY0192..."`

- `TELNYX_MODEL` — Model name to use (optional, defaults to `"Kimi-K2.5"`)
  - Example: `export TELNYX_MODEL="GLM-5.1-FP8"`

- `TELNYX_EMBEDDING_MODEL` — Embedding model name (optional, defaults to `"thenlper/gte-large"`)
  - Example: `export TELNYX_EMBEDDING_MODEL="thenlper/gte-large"`

## Quick Start

```bash
# Install the Agent Framework OpenAI package and python-dotenv
pip install agent-framework-openai python-dotenv

# Set your Telnyx API key
export TELNYX_API_KEY="your-api-key-here"

# Run the basic chat completion example
python telnyx_chat_completion.py
```

## Resources

- [Telnyx AI API Documentation](https://developers.telnyx.com/docs/api/ai)
- [Telnyx Portal](https://portal.telnyx.com/)
