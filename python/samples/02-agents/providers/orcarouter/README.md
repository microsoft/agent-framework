# OrcaRouter Examples

This folder contains examples demonstrating how to use OrcaRouter with the Agent Framework.

OrcaRouter is an OpenAI-compatible AI gateway built for both models and agents. Like OpenRouter,
it exposes a provider/model namespace across many models — but it also combines adaptive routing,
automatic failover, observability, guardrails, and agent-tool governance behind the same endpoint.
You can use it through the OpenAI-compatible Chat Completions API or the Responses API, so no
OrcaRouter-specific client package is required.

## Prerequisites

1. **Create an OrcaRouter account**: Sign up at [orcarouter.ai](https://www.orcarouter.ai) and
   obtain an API key.
2. **Pick a model**: Choose a model served by the gateway, for example `orcarouter/fusion`.
   List available models with:
   ```bash
   curl -H "Authorization: Bearer $ORCAROUTER_API_KEY" https://api.orcarouter.ai/v1/models
   ```

## Examples

| File | Description |
|------|-------------|
| [`orcarouter_agent_with_openai_chat_client.py`](orcarouter_agent_with_openai_chat_client.py) | Agent with tool calling using the OpenAI Chat Completions client pointed at the OrcaRouter gateway. Shows both streaming and non-streaming responses. |
| [`orcarouter_agent_with_responses_client.py`](orcarouter_agent_with_responses_client.py) | Agent using the OpenAI Responses client (`OpenAIChatClient`) pointed at the OrcaRouter gateway. Shows both streaming and non-streaming responses. |

## Configuration

Set the following environment variables:

- `ORCAROUTER_API_KEY`: Your OrcaRouter API key
- `ORCAROUTER_BASE_URL`: The OrcaRouter gateway base URL with `/v1/` suffix (optional, defaults to `https://api.orcarouter.ai/v1`)
  - Example: `export ORCAROUTER_BASE_URL="https://api.orcarouter.ai/v1"`
- `ORCAROUTER_MODEL`: The model name to use (optional, defaults to `orcarouter/fusion`)
  - Example: `export ORCAROUTER_MODEL="orcarouter/fusion"`

The examples fall back to sensible defaults for `ORCAROUTER_BASE_URL` and `ORCAROUTER_MODEL`, so only
`ORCAROUTER_API_KEY` is strictly required.
