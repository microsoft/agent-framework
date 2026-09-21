# TypeSafe AI Jev structured-output sample

[`jev_structured_output.py`](jev_structured_output.py) demonstrates both direct
`TypeSafeChatClient` usage and integration with an Agent Framework `Agent`.

[`function_calling.py`](function_calling.py) demonstrates a Pydantic-defined
closed-set tool executed by the standard Agent Framework function loop.

[`mcp_function_calling.py`](mcp_function_calling.py) launches
[`mcp_weather_server.py`](mcp_weather_server.py), discovers its MCP tool, and
executes it through the same TypeSafe routing path. It requires the optional
`mcp` package used by Agent Framework MCP transports.

Set `TYPESAFE_API_KEY` in `python/.env`, then run from `python/`:

```bash
uv run --env-file .env --package agent-framework-typesafe \
    python packages/typesafe/samples/jev_structured_output.py

uv run --env-file .env --package agent-framework-typesafe \
    python packages/typesafe/samples/function_calling.py

uv run --env-file .env --package agent-framework-typesafe \
    python packages/typesafe/samples/mcp_function_calling.py
```

The exact probabilities and scores vary. Both examples print a department
choice, confidence, frustration score, and urgency probability.

Function calling supports one call per run and the closed-set schema subset
documented in the package README.
