# AWS Bedrock Integration for Agent Framework

AWS Bedrock integration for Microsoft Agent Framework, providing seamless access to foundation models hosted on AWS Bedrock.

## Features

- Support for multiple model providers (Anthropic Claude, Amazon Titan, and more)
- Streaming and non-streaming responses
- Tool/function calling support
- Both Converse API and InvokeModel API
- Bearer token and AWS credentials authentication
- Full support for images and documents

## Installation

```bash
pip install agent-framework-bedrock
```

## Quick Start

### Basic Usage with Bearer Token

```python
from agent_framework_bedrock import BedrockClient

# Using bearer token (API key)
# IMPORTANT: When using bearer tokens, you must use cross-region inference profile ARNs
client = BedrockClient(
    bearer_token="your-bearer-token",
    region_name="us-east-1",
    model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0"  # Note the 'us.' prefix
)

response = await client.get_response("Hello, how are you?")
print(response.messages[0].text)
```

**Important**: Bearer tokens (API keys) require using cross-region inference profile model IDs with the region prefix (e.g., `us.anthropic.claude-3-5-sonnet-20241022-v2:0`). Direct model IDs (e.g., `anthropic.claude-3-5-sonnet-20241022-v2:0`) will fail with a ValidationException.

### Using Environment Variables

Set these environment variables:
- `AWS_BEARER_TOKEN_BEDROCK`: Your AWS bearer token
- `AWS_REGION_NAME`: AWS region (default: us-east-1)
- `AWS_CHAT_MODEL_ID`: Default model ID

```python
from agent_framework_bedrock import BedrockClient

# Automatically uses environment variables
client = BedrockClient()
response = await client.get_response("Tell me a joke")
```

### Streaming Responses

```python
async for chunk in client.get_streaming_response("Tell me a story"):
    for content in chunk.contents:
        if hasattr(content, 'text'):
            print(content.text, end="", flush=True)
```

### Tool Calling

```python
from agent_framework import ai_function

@ai_function
def get_weather(location: str) -> str:
    """Get current weather for a location."""
    return f"Weather in {location}: Sunny, 72°F"

response = await client.get_response(
    "What's the weather in San Francisco?",
    tools=[get_weather]
)
```

## Supported Models

### Anthropic Claude Models
```python
client = BedrockClient(model_id="anthropic.claude-3-5-sonnet-20241022-v2:0")
client = BedrockClient(model_id="anthropic.claude-3-sonnet-20240229-v1:0")
client = BedrockClient(model_id="anthropic.claude-3-haiku-20240307-v1:0")
```

### Amazon Titan Models
```python
client = BedrockClient(model_id="amazon.titan-text-premier-v1:0")
client = BedrockClient(model_id="amazon.titan-text-express-v1")
```

### Cross-Region Inference Profiles
```python
# Cross-region inference profiles (required for bearer token authentication)
client = BedrockClient(model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0")
client = BedrockClient(model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0")
```

**Note**: Cross-region inference profile ARNs (with region prefixes like `us.`, `eu.`, etc.) are **required** when using bearer token authentication (API keys). Standard AWS credentials can use either format.

## Authentication Methods

### Bearer Token (Primary)
```python
client = BedrockClient(bearer_token="your-token")
```

### Standard AWS Credentials
```python
client = BedrockClient(
    aws_access_key_id="your-access-key",
    aws_secret_access_key="your-secret-key"
)
```

### Default Boto3 Credential Chain
```python
# Uses ~/.aws/credentials or instance profile
client = BedrockClient()
```

## API Selection

### Converse API (Default, Recommended)
```python
client = BedrockClient(use_converse_api=True)
```

### InvokeModel API
```python
client = BedrockClient(use_converse_api=False)
```

## Configuration

All configuration can be done via constructor or environment variables:

```python
BedrockClient(
    bearer_token=None,          # AWS_BEARER_TOKEN_BEDROCK
    region_name="us-east-1",    # AWS_REGION_NAME
    model_id=None,              # AWS_CHAT_MODEL_ID
    use_converse_api=True,      # Use Converse API vs InvokeModel
    aws_access_key_id=None,     # AWS_ACCESS_KEY_ID
    aws_secret_access_key=None, # AWS_SECRET_ACCESS_KEY
    aws_session_token=None,     # AWS_SESSION_TOKEN
)
```

## Advanced Usage

### Custom Boto3 Client
```python
import boto3

bedrock_runtime = boto3.client(
    'bedrock-runtime',
    region_name='us-west-2'
)

client = BedrockClient(bedrock_client=bedrock_runtime)
```

### With Images
```python
from agent_framework import ChatMessage, DataContent

messages = [
    ChatMessage(
        role="user",
        contents=[
            TextContent(text="What's in this image?"),
            DataContent(uri=f"data:image/png;base64,{base64_image_string}", media_type="image/png")
        ]
    )
]

response = await client.get_response(messages=messages)
```

## Model Capabilities

Different models have different capabilities. The client automatically detects and handles:

- **Anthropic Claude**: Full tool calling, streaming, images, documents
- **Amazon Titan**: Streaming support, no tool calling
- **Other Models**: Generic support with automatic capability detection

## Requirements

- Python 3.10+
- boto3 >= 1.35.0
- botocore >= 1.35.0
- agent-framework-core

**Important for Bearer Token Authentication**:
- boto3 1.39.12+ is **required** for AWS_BEARER_TOKEN_BEDROCK (API key) support
- If using bearer tokens, ensure you upgrade: `pip install 'boto3>=1.39.12' 'botocore>=1.39.12'`
- Standard AWS credentials work with boto3 1.35.0+

## License

MIT License - see LICENSE file for details.
