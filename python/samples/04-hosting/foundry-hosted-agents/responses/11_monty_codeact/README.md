# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent with a
**Monty-backed CodeAct context provider** hosted using the **Responses protocol**.
The model receives one tool (`execute_code`) and runs Python inside a
[Monty](https://github.com/pydantic/monty) interpreter; the registered host
tools (`compute`, `fetch_data`) are only reachable from inside the sandbox via
typed `await compute(...)` calls or the generic `call_tool(...)` fallback.

> [!NOTE]
> `agent-framework-monty` is an **alpha** package and is not yet on PyPI. The
> `pyproject.toml` resolves it from a vendored wheel under `./wheels/` via
> `[tool.uv.sources]`. Run `./vendor-wheel.sh` once (or before any image
> rebuild) to build the wheel from the in-repo source tree. The wheel is
> gitignored.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` to create a Responses client from the project
endpoint and the model deployment. The agent supports both streaming (SSE
events) and non-streaming (JSON) response modes.

See [main.py](main.py) for the full implementation.

### CodeAct context provider

`MontyCodeActProvider` is added to the agent via `context_providers=[...]`. On
every run it injects:

- An `execute_code` tool that runs Python in the Monty interpreter.
- Dynamic CodeAct instructions describing the available host tools and DSL.

The host tools (`compute`, `fetch_data`) are **not** exposed as direct agent
tools — the model can only call them from inside `execute_code`, either as
typed async functions (`await compute(operation="multiply", a=6, b=7)`) or via
the generic `call_tool("compute", operation="multiply", a=6, b=7)` fallback.
Code is type-checked against the host tool signatures using
[ty](https://docs.astral.sh/ty/) before any tool runs.

OS-level access (filesystem, network, subprocess) is blocked inside the
sandbox; the registered host tools retain full Python access.

### Observability

Agent Framework's [native OpenTelemetry instrumentation](https://learn.microsoft.com/en-us/agent-framework/agents/observability?pivots=programming-language-python) is enabled by setting these env vars in `agent.yaml` / `agent.manifest.yaml`:

- `ENABLE_INSTRUMENTATION=true` — turns on the framework's span/metric/log emitters.
- `ENABLE_SENSITIVE_DATA=true` — includes prompts, tool inputs, tool outputs, and completions in telemetry. **Dev/test only.**

`main.py` wires Azure Monitor at startup:

1. Reads `APPLICATIONINSIGHTS_CONNECTION_STRING` (Foundry hosting injects this automatically for the project's attached Application Insights resource; set it yourself when running locally).
2. Calls `azure.monitor.opentelemetry.configure_azure_monitor(connection_string=...)` to register Azure Monitor exporters with the global OTel tracer/meter/logger providers.
3. Calls `agent_framework.observability.enable_instrumentation()` so Agent Framework emits its `invoke_agent`, `chat`, `execute_tool`, and `execute_code` spans on those providers.

Trace linking happens automatically: the Foundry hosting layer's incoming `Responses` request becomes the **parent span**, and every framework / tool span (including the `execute_code` invocation that runs Monty) becomes a child via OpenTelemetry context propagation since both layers share the same global tracer provider. In Application Insights you can click any operation and see the full tree from inbound HTTP all the way down to individual `compute(...)` / `fetch_data(...)` calls inside the Monty sandbox.

## Running the Agent Host

Because this sample uses a vendored alpha wheel + a `pyproject.toml` (not
`requirements.txt`), the parent README's `uv pip install -r requirements.txt`
flow does not apply. Use these sample-specific steps:

1. From this directory, vendor the alpha wheel:

   ```bash
   ./vendor-wheel.sh
   ```

   This builds `agent_framework_monty-*.whl` from the in-repo source tree and
   writes it to `./wheels/`.

2. Install dependencies into the local virtual env:

   ```bash
   uv sync
   ```

3. Set the environment variables described in the
   [parent README](../../README.md#running-the-agent-host-locally) (Foundry
   project endpoint, model deployment, optional Application Insights), then
   start the host:

   ```bash
   uv run python main.py
   ```

Refer to the parent README for the shared `azd` / Docker / invocation /
deployment guidance.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using
> `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the
> [parent README](../../README.md) for more details. Use this README for
> sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"`
field. Try queries that benefit from combining Python with multiple tool calls:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Fetch all users, find the admins, then multiply the count by 7. Use a single execute_code call."}'
```

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Compute the total price for one of every product in the products table. Use execute_code."}'
```

The model should respond with one `execute_code` call whose code looks like:

```python
users = await fetch_data(table="users")
admins = [u for u in users if u["role"] == "admin"]
result = await compute(operation="multiply", a=len(admins), b=7)
print(result)
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the
[Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry)
section of the README in the parent directory.
