# local_mcp — WeatherAgent served as an MCP tool

Exposes a `WeatherAgent` as a single MCP tool over the Streamable-HTTP transport
using `agent-framework-hosting` + `agent-framework-hosting-mcp`.

What this sample shows:

- `MCPChannel` mounting at `/mcp` — any MCP-compatible client (IDE, agent, tooling)
  can call the `run_agent` tool to invoke the hosted agent.
- A `run_hook` that strips all caller-supplied options (host owns model selection).
- `FileHistoryProvider` for per-session history that survives restarts.
- `call_client.py` — a second `Agent` using `MCPStreamableHTTPTool` to consume the
  hosted agent as a tool, showing end-to-end agent-to-agent via MCP.

`app:app` is a module-level Starlette ASGI app.

## Run the server

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export FOUNDRY_MODEL=gpt-4o
az login

uv sync
uv run python app.py
```

Production launch with Hypercorn:

```bash
uv run hypercorn app:app --bind 0.0.0.0:8000
```

## Call via MCP client

```bash
# Plain call:
uv run python call_client.py "What is the weather in Tokyo?"

# With a session id (continues the same conversation):
uv run python call_client.py --session my-session "What is the weather in Amsterdam?"
```

> This sample is **local-only**. The hosted agent's MCP endpoint is also
> compatible with any standard MCP client (e.g. Claude Desktop, VS Code MCP
> extension, or `mcp` CLI).
