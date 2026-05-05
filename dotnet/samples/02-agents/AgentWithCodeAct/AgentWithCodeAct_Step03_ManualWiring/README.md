# AgentWithCodeAct_Step03_ManualWiring

Shows how to wire CodeAct manually using `HyperlightExecuteCodeFunction` as a
direct agent tool instead of via an `AIContextProvider`. This is useful when
the sandbox's tool surface and capabilities are fixed for the agent's
lifetime, avoiding per-run snapshot/restore of the provider registry.

## Configuration

| Variable                       | Description                                                                               |
|--------------------------------|-------------------------------------------------------------------------------------------|
| `AZURE_OPENAI_ENDPOINT`        | Azure OpenAI endpoint. Required.                                                          |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Azure OpenAI deployment. Defaults to `gpt-5.4-mini`.                                      |
| `HYPERLIGHT_PYTHON_GUEST_PATH` | Absolute path to the Hyperlight Python guest module (`.wasm` or `.aot` file). Required.   |

## Run

```shell
cd AgentWithCodeAct_Step03_ManualWiring
dotnet run
```
