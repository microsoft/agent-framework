# Local CodeAct samples

These samples show how to wire `agent-framework-local-codeact` into an Agent
Framework application.

Local CodeAct runs LLM-generated Python in the agent environment. Use these
patterns only in an externally sandboxed environment such as a Foundry hosted
agent, container, or VM.

| Sample | Description |
| --- | --- |
| `foundry_hosted_agent.py` | Hosts a `FoundryChatClient`-backed agent with `LocalCodeActProvider` behind `ResponsesHostServer`. Registers `compute` and `fetch_data` as sandbox-only host tools the model reaches via `call_tool(...)` from inside `execute_code`. Use it together with the shared Foundry hosted-agent setup in [`python/samples/04-hosting/foundry-hosted-agents/responses`](../../../samples/04-hosting/foundry-hosted-agents/responses) for the Dockerfile, manifest, and deployment workflow used by the other Responses-based hosted agents. |
| `local_execute_code.py` | Invokes `LocalExecuteCodeTool` directly with host tools, explicit environment variables, file mounts, subprocess mode, the Python executable path, and execution limits. |

Run the local sample from the `python/` directory:

```bash
uv run --package agent-framework-local-codeact packages/local_codeact/samples/local_execute_code.py
```

Run the Foundry hosted-agent sample (requires `FOUNDRY_PROJECT_ENDPOINT` and
`AZURE_AI_MODEL_DEPLOYMENT_NAME`, plus `az login` for `DefaultAzureCredential`).
Use it together with the shared Foundry hosted-agent setup in
[`python/samples/04-hosting/foundry-hosted-agents/responses`](../../../samples/04-hosting/foundry-hosted-agents/responses)
for the Dockerfile, manifest, and deployment workflow used by the other
Responses-based hosted agents:

```bash
uv run --package agent-framework-local-codeact packages/local_codeact/samples/foundry_hosted_agent.py
```

Then send a request:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Fetch all users, find the admins, multiply 7 by 6, and print the users, admins and multiplication result. Use execute_code with call_tool(...)."}'
```
