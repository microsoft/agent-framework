# MLflow AI Gateway Examples

This folder contains examples demonstrating how to use the [MLflow AI Gateway](https://mlflow.org/docs/latest/genai/governance/ai-gateway/) with the Agent Framework.

## What is MLflow AI Gateway?

MLflow AI Gateway (MLflow ≥ 3.0) is a database-backed LLM proxy built into the MLflow tracking server. It provides a unified API across multiple LLM providers — OpenAI, Anthropic, Gemini, Mistral, Bedrock, Ollama, and more — with built-in:

- **Secrets management** — provider API keys stored encrypted on the server
- **Fallback & retry** — automatic failover to backup models on failure
- **Traffic splitting** — A/B test by routing percentages of requests to different models
- **Budget tracking** — per-endpoint or per-user token budgets
- **Usage tracing** — every call logged as an MLflow trace automatically

All gateway features are configured through the MLflow UI. Your application code stays the same regardless of which underlying LLM provider the gateway routes to.

## Prerequisites

1. **Install MLflow** (using [`uv`](https://docs.astral.sh/uv/), which Agent Framework uses):

    ```bash
    uv pip install 'mlflow[genai]'
    ```

    Or run it directly with `uvx` (no install needed):

    ```bash
    uvx --from 'mlflow[genai]' mlflow server --host 127.0.0.1 --port 5000
    ```

2. **Start the MLflow server** (if you didn't use `uvx` above):

    ```bash
    mlflow server --host 127.0.0.1 --port 5000
    ```

3. **Create a gateway endpoint** in the MLflow UI at [http://localhost:5000](http://localhost:5000). Navigate to **AI Gateway → Create Endpoint**, select a provider (e.g., OpenAI) and model (e.g., `gpt-4o-mini`), and enter your provider API key. The key is stored encrypted on the server.

    See the [MLflow AI Gateway documentation](https://mlflow.org/docs/latest/genai/governance/ai-gateway/endpoints/) for details on endpoint configuration.

## Recommended Approach

Since MLflow AI Gateway exposes an OpenAI-compatible endpoint at `/gateway/openai/v1`, you can connect Agent Framework to it using the existing `OpenAIChatClient` with a custom `base_url` — no extra packages required beyond the OpenAI integration.

## Examples

| File | Description |
|------|-------------|
| [`mlflow_gateway_with_openai_chat_client.py`](mlflow_gateway_with_openai_chat_client.py) | Connect an Agent Framework agent to MLflow AI Gateway via the OpenAI-compatible endpoint. Shows both streaming and non-streaming responses with tool calling. |

## Configuration

Set the following environment variables before running the example:

- `MLFLOW_GATEWAY_ENDPOINT`: The base URL for the gateway's OpenAI-compatible endpoint (must include the `/gateway/openai/v1/` suffix)
  - Example: `export MLFLOW_GATEWAY_ENDPOINT="http://localhost:5000/gateway/openai/v1/"`

- `MLFLOW_GATEWAY_MODEL`: The gateway endpoint name you created in the MLflow UI
  - Example: `export MLFLOW_GATEWAY_MODEL="my-chat-endpoint"`

## Switching Providers Without Code Changes

A key benefit of using MLflow AI Gateway is that you can change the underlying LLM provider by reconfiguring the gateway endpoint in the MLflow UI — your Agent Framework code stays the same. For example, the same agent can route to:

- An OpenAI-backed endpoint for production
- An Anthropic-backed endpoint for fallback
- A local Ollama-backed endpoint for development

All controlled by the gateway's endpoint configuration.
