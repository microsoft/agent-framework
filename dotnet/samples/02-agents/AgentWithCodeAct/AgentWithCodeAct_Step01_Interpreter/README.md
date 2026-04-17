# AgentWithCodeAct_Step01_Interpreter

A minimal CodeAct sample. The agent uses `HyperlightCodeActProvider` as a
sandboxed Python interpreter: when the user asks something quantitative, the
model writes Python and invokes the `execute_code` tool rather than answering
from memory.

## Configuration

| Variable                       | Description                                                                               |
|--------------------------------|-------------------------------------------------------------------------------------------|
| `AZURE_OPENAI_ENDPOINT`        | Azure OpenAI endpoint. Required.                                                          |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Azure OpenAI deployment. Defaults to `gpt-5.4-mini`.                                      |
| `HYPERLIGHT_PYTHON_GUEST_PATH` | Absolute path to the Hyperlight Python guest module (`.wasm` or `.aot` file). Required.   |

Authentication uses `DefaultAzureCredential`.

## Run

```shell
cd AgentWithCodeAct_Step01_Interpreter
dotnet run
```
