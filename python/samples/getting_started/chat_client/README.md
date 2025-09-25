# Chat Client Examples

This folder contains simple examples demonstrating direct usage of various chat clients.

## Examples

| File | Description |
|------|-------------|
| [`azure_assistants_client.py`](azure_assistants_client.py) | Direct usage of Azure Assistants Client for basic chat interactions with Azure OpenAI assistants. |
| [`azure_chat_client.py`](azure_chat_client.py) | Direct usage of Azure Chat Client for chat interactions with Azure OpenAI models. |
| [`azure_responses_client.py`](azure_responses_client.py) | Direct usage of Azure Responses Client for structured response generation with Azure OpenAI models. |
| [`chat_response_cancellation.py`](chat_response_cancellation.py) | Demonstrates how to cancel chat responses during streaming, showing proper cancellation handling and cleanup. |
| [`azure_ai_chat_client.py`](azure_ai_chat_client.py) | Direct usage of Azure AI Chat Client for chat interactions with Azure AI models. |
| [`openai_assistants_client.py`](openai_assistants_client.py) | Direct usage of OpenAI Assistants Client for basic chat interactions with OpenAI assistants. |
| [`openai_chat_client.py`](openai_chat_client.py) | Direct usage of OpenAI Chat Client for chat interactions with OpenAI models. |
| [`openai_responses_client.py`](openai_responses_client.py) | Direct usage of OpenAI Responses Client for structured response generation with OpenAI models. |

## Environment Variables

Depending on which client you're using, set the appropriate environment variables:

**For Azure clients:**
- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: The name of your Azure OpenAI chat deployment
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`: The name of your Azure OpenAI responses deployment

**For Azure AI client:**
- `AZURE_AI_PROJECT_ENDPOINT`: Your Azure AI project endpoint
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: The name of your model deployment

**For OpenAI clients:**
- `OPENAI_API_KEY`: Your OpenAI API key
- `OPENAI_CHAT_MODEL_ID`: The OpenAI model to use for chat clients (e.g., `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`)
- `OPENAI_RESPONSES_MODEL_ID`: The OpenAI model to use for responses clients (e.g., `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`)
