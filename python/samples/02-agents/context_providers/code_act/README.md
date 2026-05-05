# Hyperlight CodeAct context provider

Demonstrates the provider-owned [Hyperlight](https://github.com/hyperlight-dev/hyperlight)
CodeAct flow. `HyperlightCodeActProvider` injects an `execute_code` tool into the
agent and keeps the registered sandbox tools (`compute`, `fetch_data`) hidden
from the model — the model must call them from inside the sandbox using
`call_tool(...)`.

## Installation

```bash
pip install agent-framework agent-framework-hyperlight --pre
```

> The Hyperlight Wasm backend is currently published only for `linux/x86_64` and
> `win32/AMD64` with Python `<3.14`. On other platforms `execute_code` will fail
> at runtime when it tries to create the sandbox.

## Prerequisites

- An Azure AI Foundry project endpoint (`FOUNDRY_PROJECT_ENDPOINT`)
- A deployed model (`FOUNDRY_MODEL`)
- Azure CLI authenticated (`az login`)

## Run

```bash
python code_act.py
```

See [`code_act.py`](code_act.py) for the full annotated example.
