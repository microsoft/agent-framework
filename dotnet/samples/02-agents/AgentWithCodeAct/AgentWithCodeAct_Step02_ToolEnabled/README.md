# AgentWithCodeAct_Step02_ToolEnabled

Demonstrates adding provider-owned tools to `HyperlightCodeActProvider`. Those
tools are **only** available to code running inside the sandbox via
`call_tool("<name>", ...)` — they are never exposed to the model as direct
tools. This lets the model orchestrate multiple tool calls in a single Python
block.

One tool (`send_email`) is wrapped in `ApprovalRequiredAIFunction`, which causes
the entire `execute_code` invocation to require user approval when that tool
is configured.

## Configuration

| Variable                       | Description                                                                               |
|--------------------------------|-------------------------------------------------------------------------------------------|
| `AZURE_OPENAI_ENDPOINT`        | Azure OpenAI endpoint. Required.                                                          |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Azure OpenAI deployment. Defaults to `gpt-5.4-mini`.                                      |
| `HYPERLIGHT_PYTHON_GUEST_PATH` | Absolute path to the Hyperlight Python guest module (`.wasm` or `.aot` file). Required.   |

## Run

```shell
cd AgentWithCodeAct_Step02_ToolEnabled
dotnet run
```

## Planned follow-up

A more realistic "upload a file (e.g. an Excel workbook), have the agent
analyze it with code" sample is planned as a separate step that will use
`HostInputDirectory` together with a guest tool capable of reading the
uploaded file. It will be added in a follow-up PR once the corresponding
guest module support is in place.
