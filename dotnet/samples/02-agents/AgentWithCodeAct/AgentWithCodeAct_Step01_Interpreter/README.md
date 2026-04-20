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

## Getting the guest module

The Python guest module is built from the
[hyperlight-dev/hyperlight-sandbox](https://github.com/hyperlight-dev/hyperlight-sandbox)
repository — see its README for the exact `cargo`/`just` invocations and
the location of the resulting `.wasm` / `.aot` file. Set
`HYPERLIGHT_PYTHON_GUEST_PATH` to the absolute path of that artifact
before running the sample.

Hyperlight requires a hardware virtualization back end on the host:
KVM on Linux or WHP (Windows Hypervisor Platform) on Windows.

## Run

```shell
cd AgentWithCodeAct_Step01_Interpreter
dotnet run
```
