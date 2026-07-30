# Azure Provider Samples

This folder contains Azure-backed samples for the generic OpenAI clients in
`agent_framework.openai`.

## Chat Completions API samples (`OpenAIChatCompletionClient`)

| File | Description |
|------|-------------|
| [`openai_chat_completion_client_basic.py`](openai_chat_completion_client_basic.py) | Basic Azure chat completions sample using explicit Azure settings and `credential=AzureCliCredential()`. |
| [`openai_chat_completion_client_with_explicit_settings.py`](openai_chat_completion_client_with_explicit_settings.py) | Azure chat completions sample with explicit settings. |
| [`openai_chat_completion_client_with_function_tools.py`](openai_chat_completion_client_with_function_tools.py) | Azure chat completions sample with function tools. |
| [`openai_chat_completion_client_with_session.py`](openai_chat_completion_client_with_session.py) | Azure chat completions sample with session management. |

## Responses API samples (`OpenAIChatClient`)

| File | Description |
|------|-------------|
| [`openai_client_basic.py`](openai_client_basic.py) | Basic Azure responses sample using explicit settings and `credential=AzureCliCredential()`. |
| [`openai_client_with_function_tools.py`](openai_client_with_function_tools.py) | Azure responses sample with function tools. |
| [`openai_client_with_session.py`](openai_client_with_session.py) | Azure responses sample with session management. |
| [`openai_client_with_structured_output.py`](openai_client_with_structured_output.py) | Azure responses sample with structured output. |

## Environment Variables

Set these before running the Azure provider samples:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_MODEL`

Optionally, you can also set:

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_BASE_URL`

These Azure samples are written around explicit Azure inputs such as
`credential=AzureCliCredential()`, so they stay on Azure even if `OPENAI_API_KEY` is also present.

## Optional Dependencies

Credential-based samples require `azure-identity`:

```bash
pip install azure-identity
```

Run `az login` before executing the credential-based samples.
