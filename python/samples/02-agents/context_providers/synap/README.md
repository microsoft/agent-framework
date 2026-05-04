# Synap Context Provider Sample

Demonstrates [SynapContextProvider](https://docs.maximem.ai/integrations/microsoft-agent) — a Microsoft Agent Framework `ContextProvider` backed by [Synap](https://maximem.ai), a managed memory layer for AI agents.

## How It Works

`SynapContextProvider` implements two lifecycle hooks:
- **`before_run`**: fetches Synap context relevant to the user's input and appends it to the agent's instructions via `context.extend_instructions(...)`
- **`after_run`**: records input and response messages to Synap via `sdk.conversation.record_message(...)` for future retrieval

Read failures degrade gracefully — a Synap outage never breaks the agent run. Write failures are logged but not re-raised.

## Setup

```bash
pip install maximem-synap-microsoft-agent
```

Set `SYNAP_API_KEY` (get one at [synap.maximem.ai](https://synap.maximem.ai)).

## Run

```bash
python synap_basic.py
```

## More Resources

- [Synap Documentation](https://docs.maximem.ai)
- [Microsoft Agent Framework Integration Guide](https://docs.maximem.ai/integrations/microsoft-agent)
- [Dashboard](https://synap.maximem.ai)
- [PyPI: maximem-synap-microsoft-agent](https://pypi.org/project/maximem-synap-microsoft-agent/)
