# Anthropic Examples

This folder contains examples demonstrating how to use Anthropic's Claude models with the Agent Framework.

## Examples

| File | Description |
|------|-------------|
| [`anthropic_basic.py`](anthropic_basic.py) | Demonstrates how to setup a simple agent using the AnthropicClient, with both streaming and non-streaming responses. |
| [`anthropic_advanced.py`](anthropic_advanced.py) | Shows advanced usage of the AnthropicClient, including hosted tools and `thinking`. |
| [`anthropic_skills.py`](anthropic_skills.py) | Illustrates how to use Anthropic-managed Skills with an agent, including the Code Interpreter tool and file generation and saving. |
| [`anthropic_foundry.py`](anthropic_foundry.py) | Example of using Azure AI Foundry's Anthropic integration with the Agent Framework. |

## Supported Backends

The `AnthropicClient` supports multiple backends for accessing Claude models:

| Backend | Description | Detection |
|---------|-------------|-----------|
| `anthropic` | Direct Anthropic API | `ANTHROPIC_API_KEY` is set |
| `foundry` | Azure AI Foundry | `ANTHROPIC_FOUNDRY_API_KEY` or `ANTHROPIC_FOUNDRY_RESOURCE` is set |
| `vertex` | Google Vertex AI | `ANTHROPIC_VERTEX_ACCESS_TOKEN` or `ANTHROPIC_VERTEX_PROJECT_ID` is set |
| `bedrock` | AWS Bedrock | `ANTHROPIC_AWS_ACCESS_KEY_ID` or `ANTHROPIC_AWS_PROFILE` is set |

The backend is automatically detected based on which credentials are available, with precedence in the order listed above. You can also explicitly specify the backend:

```python
client = AnthropicClient(backend="foundry")
```

Or via environment variable:

```bash
export ANTHROPIC_CHAT_CLIENT_BACKEND=foundry
```

## Environment Variables

### Common (all backends)

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_CHAT_MODEL_ID` | The Claude model to use (e.g., `claude-sonnet-4-5-20250929`) |
| `ANTHROPIC_CHAT_CLIENT_BACKEND` | Explicit backend selection: `anthropic`, `foundry`, `vertex`, or `bedrock` |

### Anthropic API (Direct)

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key ([get one here](https://console.anthropic.com/)) |
| `ANTHROPIC_BASE_URL` | Optional custom base URL |

### Azure AI Foundry

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_FOUNDRY_API_KEY` | Your Foundry Anthropic API key |
| `ANTHROPIC_FOUNDRY_RESOURCE` | Azure resource name (used to construct endpoint URL) |
| `ANTHROPIC_FOUNDRY_BASE_URL` | Optional custom endpoint URL |

### Google Vertex AI

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_VERTEX_ACCESS_TOKEN` | Google access token |
| `ANTHROPIC_VERTEX_PROJECT_ID` | GCP project ID |
| `CLOUD_ML_REGION` | GCP region (e.g., `us-central1`) |
| `ANTHROPIC_VERTEX_BASE_URL` | Optional custom endpoint URL |

### AWS Bedrock

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_AWS_ACCESS_KEY_ID` | AWS access key ID |
| `ANTHROPIC_AWS_SECRET_ACCESS_KEY` | AWS secret access key |
| `ANTHROPIC_AWS_SESSION_TOKEN` | Optional AWS session token |
| `ANTHROPIC_AWS_PROFILE` | AWS profile name (alternative to access keys) |
| `ANTHROPIC_AWS_REGION` | AWS region (e.g., `us-east-1`) |
| `ANTHROPIC_BEDROCK_BASE_URL` | Optional custom endpoint URL |
