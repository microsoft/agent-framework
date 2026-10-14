# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent with a
**Monty-backed CodeAct context provider** hosted using the **Responses protocol**.
The model receives one tool (`execute_code`) and runs Python inside a
[Monty](https://github.com/pydantic/monty) interpreter; the registered host
tools (`compute`, `fetch_data`) are only reachable from inside the sandbox via
typed `await compute(...)` calls or the generic `call_tool(...)` fallback.

> [!NOTE]
> `agent-framework-monty` is a **beta** package. Its dependency is declared in
> `main.py`'s PEP 723 script metadata; use `--prerelease=allow` when running it.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` to create a Responses client from the project
endpoint and the model deployment. The agent supports both streaming (SSE
events) and non-streaming (JSON) response modes.

See [main.py](main.py) for the full implementation.

`ResponsesHostServer(agent=create_agent, history_source="agent_server")`
constructs a fresh CodeAct provider, client and credential for each request.
No interpreter/provider instance, tool connection or model client is reused
from an earlier caller. The factory's client context closes its owned SDK
transports and credential after the request. Local calls use
`AzureCliCredential`; hosted calls use managed identity.

The host supplies conversation history and disables inner model storage. The
registered host tools operate only on the explicit **shared illustrative data**
in this sample, not user-private external records. Real tools must enforce
their own trusted user/sandbox authorization; Monty's interpreter isolation
does not scope an external database or token.

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
- `ENABLE_SENSITIVE_DATA=false` — the default; sensitive payload capture is opt-in for approved debugging only.

The Foundry runtime manages exporters when hosted or launched through
`azd ai agent run`. This entry point does **not** install Azure Monitor exporters
at startup. A direct local `python main.py` run needs separately configured
exporters if exported telemetry is desired. Do not log platform identities or
tokens, and do not enable sensitive payloads in a shared production sample.

Trace linking happens automatically: the Foundry hosting layer's incoming `Responses` request becomes the **parent span**, and every framework / tool span (including the `execute_code` invocation that runs Monty) becomes a child via OpenTelemetry context propagation since both layers share the same global tracer provider. In Application Insights you can click any operation and see the full tree from inbound HTTP all the way down to individual `compute(...)` / `fetch_data(...)` calls inside the Monty sandbox.

## Running the Agent Host

Set the environment variables described in the
[parent README](../../README.md#running-the-agent-host-locally), then run using
the dependencies declared in the script:

```bash
uv run --script --prerelease=allow main.py
```

Additional sample imports belong in inline script metadata, not a workspace,
package or sample `pyproject.toml`. Before the coordinated hosting beta is
published, use the current workspace's installed packages
(`uv run --no-sync python main.py`) rather than assuming an older PyPI wheel
contains the current hosting API.

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

Monty does not require KVM. The separate
[Hyperlight container example](../../../container/hyperlight_codeact/) requires
KVM/hypervisor access unavailable in the default Foundry runtime; this sample
does not validate or claim that Hyperlight deployment works.
