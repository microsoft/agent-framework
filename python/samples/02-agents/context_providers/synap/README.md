# Synap Context Provider Sample

Demonstrates [SynapContextProvider](https://docs.maximem.ai/integrations/microsoft-agent) — a Microsoft Agent Framework `ContextProvider` backed by [Synap](https://maximem.ai), a managed memory layer for AI agents.

## How It Works

`SynapContextProvider` implements two lifecycle hooks:
- **`before_run`**: fetches Synap context relevant to the user's input and appends it to the agent's instructions
- **`after_run`**: records input and response messages to Synap via `sdk.conversation.record_message(...)` for future retrieval

Read failures degrade gracefully. Write failures are logged but never re-raised.

## Setup

**1. Install dependencies**

```bash
pip install maximem-synap-microsoft-agent azure-identity python-dotenv
```

**2. Configure Azure credentials**

This sample uses [Azure AI Foundry](https://ai.azure.com) as the model provider. Run `az login` to authenticate, or replace `AzureCliCredential` with your preferred credential.

Set the following in a `.env` file or as environment variables:

```
AZURE_AI_FOUNDRY_PROJECT_ENDPOINT=<your-foundry-endpoint>
```

**3. Get a Synap API key**

Sign up at [synap.maximem.ai](https://synap.maximem.ai) and set `SYNAP_API_KEY` in your `.env`, or pass it directly to `MaximemSynapSDK(api_key=...)`.

## Run

```bash
python synap_basic.py
```

## More Resources

- [Synap Documentation](https://docs.maximem.ai)
- [Microsoft Agent Framework Integration Guide](https://docs.maximem.ai/integrations/microsoft-agent)
- [Dashboard](https://synap.maximem.ai)
- [PyPI: maximem-synap-microsoft-agent](https://pypi.org/project/maximem-synap-microsoft-agent/)
- [Open source integration package](https://github.com/maximem-ai/maximem_synap_sdk/tree/main/packages/integrations)
