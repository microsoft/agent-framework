# Get Started with Microsoft Agent Framework Anthropic

Please install this package via pip:

```bash
pip install agent-framework-anthropic --pre
```

## Anthropic Integration

The Anthropic integration enables communication with Anthropic's Claude models through multiple backends:

- **Anthropic API** (direct) - Default, highest precedence
- **Azure AI Foundry** - Claude models via Azure
- **Google Vertex AI** - Claude models via Google Cloud
- **AWS Bedrock** - Claude models via AWS

### Basic Usage Example

```python
from agent_framework_anthropic import AnthropicClient

# Using environment variables (ANTHROPIC_API_KEY, ANTHROPIC_CHAT_MODEL_ID)
client = AnthropicClient()

# Or with explicit parameters
client = AnthropicClient(
    api_key="sk-...",
    model_id="claude-sonnet-4-5-20250929",
)
```

### Multi-Backend Support

The client automatically detects which backend to use based on available credentials, or you can explicitly specify the backend:

```python
# Explicit backend selection
client = AnthropicClient(backend="anthropic")  # Direct Anthropic API
client = AnthropicClient(backend="foundry")    # Azure AI Foundry
client = AnthropicClient(backend="vertex")     # Google Vertex AI
client = AnthropicClient(backend="bedrock")    # AWS Bedrock
```

### Environment Variables

#### Anthropic API (Direct)
| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ANTHROPIC_CHAT_MODEL_ID` | Model ID (e.g., `claude-sonnet-4-5-20250929`) |
| `ANTHROPIC_BASE_URL` | Optional custom base URL |

#### Azure AI Foundry
| Variable | Description |
|----------|-------------|
| `ANTHROPIC_FOUNDRY_API_KEY` | Foundry API key (or use `ad_token_provider`) |
| `ANTHROPIC_FOUNDRY_RESOURCE` | Azure resource name |
| `ANTHROPIC_FOUNDRY_BASE_URL` | Optional custom endpoint URL |
| `ANTHROPIC_CHAT_MODEL_ID` | Model ID |

#### Google Vertex AI
| Variable | Description |
|----------|-------------|
| `ANTHROPIC_VERTEX_ACCESS_TOKEN` | Google access token (or use `google_credentials`) |
| `ANTHROPIC_VERTEX_PROJECT_ID` | GCP project ID |
| `CLOUD_ML_REGION` | GCP region (e.g., `us-central1`) |
| `ANTHROPIC_VERTEX_BASE_URL` | Optional custom endpoint URL |
| `ANTHROPIC_CHAT_MODEL_ID` | Model ID |

#### AWS Bedrock
| Variable | Description |
|----------|-------------|
| `ANTHROPIC_AWS_ACCESS_KEY_ID` | AWS access key |
| `ANTHROPIC_AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `ANTHROPIC_AWS_SESSION_TOKEN` | Optional session token |
| `ANTHROPIC_AWS_PROFILE` | AWS profile name (alternative to access keys) |
| `ANTHROPIC_AWS_REGION` | AWS region |
| `ANTHROPIC_BEDROCK_BASE_URL` | Optional custom endpoint URL |
| `ANTHROPIC_CHAT_MODEL_ID` | Model ID |

#### Backend Selection
| Variable | Description |
|----------|-------------|
| `ANTHROPIC_CHAT_CLIENT_BACKEND` | Explicit backend: `anthropic`, `foundry`, `vertex`, or `bedrock` |

### Examples

See the [Anthropic agent examples](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents/anthropic/) which demonstrate:

- Connecting to Anthropic with an agent
- Streaming and non-streaming responses
- Using different backends (Foundry, Vertex, Bedrock)
- Advanced features like hosted tools and thinking
