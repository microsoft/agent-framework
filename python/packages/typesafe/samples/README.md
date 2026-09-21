# TypeSafe AI Jev structured-output sample

[`jev_structured_output.py`](jev_structured_output.py) demonstrates both direct
`TypeSafeChatClient` usage and integration with an Agent Framework `Agent`.

Set `TYPESAFE_API_KEY` in `python/.env`, then run from `python/`:

```bash
uv run --env-file .env --package agent-framework-typesafe \
    python packages/typesafe/samples/jev_structured_output.py
```

The exact probabilities and scores vary. Both examples print a department
choice, confidence, frustration score, and urgency probability.

Agent Framework may warn that the client does not support function invocation.
This is expected because TypeSafe System One models do not expose tool calling.
