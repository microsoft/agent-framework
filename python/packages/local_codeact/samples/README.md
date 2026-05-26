# Local CodeAct samples

These samples show how to wire `agent-framework-local-codeact` into an Agent
Framework application.

Local CodeAct runs LLM-generated Python in the agent environment. Use these
patterns only in an externally sandboxed environment such as a Foundry hosted
agent, container, or VM.

| Sample | Description |
| --- | --- |
| `foundry_hosted_agent.py` | Adds `LocalCodeActProvider` to an agent before wrapping it with `ResponsesHostServer`. |
| `local_execute_code.py` | Invokes `LocalExecuteCodeTool` directly with host tools, explicit environment variables, file mounts, subprocess mode, the Python executable path, and execution limits. |

Run the local sample from the `python/` directory:

```bash
uv run --package agent-framework-local-codeact packages/local_codeact/samples/local_execute_code.py
```
