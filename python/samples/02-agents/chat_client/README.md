# Chat Client Examples

This folder contains examples for direct chat client usage patterns.

## Examples

| File | Description |
|------|-------------|
| [`built_in_chat_clients.py`](built_in_chat_clients.py) | Consolidated sample for built-in chat clients. Uses `get_client()` to create the selected client and pass it to `main()`. |
| [`chat_response_cancellation.py`](chat_response_cancellation.py) | Demonstrates how to cancel chat responses during streaming, showing proper cancellation handling and cleanup. |
| [`custom_chat_client.py`](custom_chat_client.py) | Demonstrates how to create custom chat clients by extending the `BaseChatClient` class. Shows a `EchoingChatClient` implementation and how to integrate it with `Agent` using the `as_agent()` method. |

## Selecting a built-in client

`built_in_chat_clients.py` starts with:

```python
asyncio.run(main("openai_chat"))
```

Change the argument to pick a client:

- `openai_chat`
- `openai_responses`
- `openai_assistants`
- `anthropic`
- `ollama`
- `bedrock`
- `azure_openai_chat`
- `azure_openai_responses`
- `azure_openai_responses_foundry`
- `azure_openai_assistants`
- `azure_ai_agent`

Example:

```bash
uv run samples/02-agents/chat_client/built_in_chat_clients.py
```

## Environment Variables

Depending on the selected client, set the appropriate environment variables:

**For Azure clients:**
- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: The name of your Azure OpenAI chat deployment
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`: The name of your Azure OpenAI responses deployment

**For Azure OpenAI Foundry responses client (`azure_openai_responses_foundry`):**
- `AZURE_AI_PROJECT_ENDPOINT`: Your Azure AI project endpoint
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`: The name of your Azure OpenAI responses deployment

**For Azure AI agent client (`azure_ai_agent`):**
- `AZURE_AI_PROJECT_ENDPOINT`: Your Azure AI project endpoint
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: The name of your model deployment (used by `azure_ai_agent`)

**For OpenAI clients:**
- `OPENAI_API_KEY`: Your OpenAI API key
- `OPENAI_CHAT_MODEL_ID`: The OpenAI model for `openai_chat` and `openai_assistants`
- `OPENAI_RESPONSES_MODEL_ID`: The OpenAI model for `openai_responses`

**For Anthropic client (`anthropic`):**
- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `ANTHROPIC_CHAT_MODEL_ID`: The Anthropic model ID (for example, `claude-sonnet-4-5`)

**For Ollama client (`ollama`):**
- `OLLAMA_HOST`: Ollama server URL (defaults to `http://localhost:11434` if unset)
- `OLLAMA_MODEL_ID`: Ollama model name (for example, `mistral`, `qwen2.5:8b`)

**For Bedrock client (`bedrock`):**
- `BEDROCK_CHAT_MODEL_ID`: Bedrock model ID (for example, `anthropic.claude-3-5-sonnet-20240620-v1:0`)
- `BEDROCK_REGION`: AWS region (defaults to `us-east-1` if unset)
- AWS credentials via standard environment variables (for example, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
