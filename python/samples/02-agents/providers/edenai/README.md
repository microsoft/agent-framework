# Eden AI Samples

Samples for the Eden AI provider using `EdenAIChatClient`.

Eden AI is a gateway to many model providers behind one OpenAI compatible API and a single key. Models use the `provider/model` format, for example `openai/gpt-4o-mini` or `anthropic/claude-sonnet-4-5`.

## Setup

```bash
pip install agent-framework-edenai --pre
```

Set the following environment variables (a `.env` file is supported):

- `EDENAI_API_KEY`: your Eden AI API key (get one at https://www.edenai.co).
- `EDENAI_MODEL`: the `provider/model` to use, for example `openai/gpt-4o-mini`.
- `EDENAI_BASE_URL`: optional, defaults to `https://api.edenai.run/v3`.

## Files

| File | What it shows |
| --- | --- |
| [`edenai_chat_client.py`](edenai_chat_client.py) | Basic `EdenAIChatClient` usage with a function tool. |
